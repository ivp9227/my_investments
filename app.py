from flask import Flask, render_template, request, flash, redirect, url_for
from datetime import date, datetime
import os
from decimal import Decimal
from markupsafe import Markup
import signal
import sys

from models import *
from support_functions import *

app = Flask(__name__)
app.secret_key = os.urandom(24)

# настройка базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)  # интегрирование db в приложение


@app.context_processor
def inject_common_data():
    """Контекстный процессор для доступа переменных в функциях представления"""

    assets = MyAssets.query.all()
    asset_types = AssetsList.query.all()
    brokers = Brokers.query.all()
    operations = Operations.query.all()

    total_balance = db.session.query(func.sum(Brokers.account_balance)).scalar() or 0
    portfolio_value = (db.session.query(func.sum(MyAssets.current_cost_asset)).scalar() or 0) + total_balance
    income_all_time = db.session.query(func.sum(TradeHistory.total_return)).scalar() or 0

    updating_data_financial_instruments()
    return dict(portfolio_value=portfolio_value, transform_number=transform_number, total_balance=total_balance,
                asset_types=asset_types, brokers=brokers, operations=operations, assets=assets,
                income_all_time=income_all_time)


def data_recording_operations_report(purchase_date, broker_id, amount, operation_type_id, note=''):
    operation = OperationsReport(
        operation_date=purchase_date,
        broker_id=broker_id,
        amount=amount,
        operation_type_id=operation_type_id,
        note=note)
    db.session.add(operation)
    db.session.commit()


def partial_data_recording_trade_history(brokerage_account_id, asset_type_id, asset_name, isin, ticker,
                                         purchase_date, cost_one_unit, quantity, bond_amortization,
                                         selling_price_one_unit, sale_date):
    data = TradeHistory(
        brokerage_account_id=brokerage_account_id,
        asset_type_id=asset_type_id,
        asset_name=asset_name,
        isin=isin,
        ticker=ticker,
        purchase_date=purchase_date,
        cost_one_unit=cost_one_unit,
        quantity=quantity,
        bond_amortization=bond_amortization,
        selling_price_one_unit=selling_price_one_unit,
        selling_price_asset=quantity * selling_price_one_unit,
        sale_date=sale_date,
        holding_days=(func.julianday(sale_date) - func.julianday(purchase_date)).cast(db.Integer) + 1
    )
    db.session.add(data)
    db.session.commit()


@app.route('/')
def index():
    assets = MyAssets.query.order_by(MyAssets.asset_type_id).all()
    return render_template('index.html', assets=assets)


@app.route('/purchase_asset', methods=["POST", "GET"])
def purchase_asset():
    if request.method == "POST":
        try:
            broker_id = int(request.form.get('broker_id'))
            asset_name = request.form.get('asset_name').rstrip()
            asset_type_id = int(request.form.get('asset_type'))
            isin = request.form.get('isin').rstrip()
            purchase_date = datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d')
            cost_one_unit = Decimal(request.form.get('cost_one_unit').replace(',', '.'))
            quantity = int(request.form.get('quantity'))
            brokerage_fee = Decimal(request.form.get('brokerage_fee').replace(',', '.'))

            costs = Decimal(cost_one_unit * quantity + brokerage_fee)
            brokerage_account = Brokers.query.get(broker_id)

            if brokerage_account.account_balance < costs:
                flash('Недостаточно средств', 'error')
                return redirect(url_for('purchase_asset'))

            brokerage_account.account_balance -= costs

            existing_asset = db.session.query(MyAssets).filter(
                MyAssets.brokerage_account_id == broker_id,
                MyAssets.isin == isin,
                MyAssets.asset_name == asset_name
            ).first()

            if existing_asset:
                existing_asset.quantity += quantity
                existing_asset.cost_one_unit = (existing_asset.cost_one_unit + cost_one_unit) / 2
                existing_asset.brokerage_fee += brokerage_fee
                db.session.commit()
                existing_asset.total_purchase_cost = existing_asset.cost_one_unit * existing_asset.quantity
                existing_asset.current_cost_one_unit = cost_one_unit

                flash(Markup(f'Данные обновлены --><br>{asset_name}<br>ISIN: {isin}'), 'success')
            else:
                new_asset = MyAssets(
                    brokerage_account_id=broker_id,
                    asset_type_id=asset_type_id,
                    asset_name=asset_name,
                    isin=isin,
                    ticker=request.form.get('ticker') or '-',
                    purchase_date=purchase_date,
                    cost_one_unit=cost_one_unit,
                    quantity=quantity,
                    total_purchase_cost=cost_one_unit * quantity,
                    brokerage_fee=brokerage_fee,
                    dividends_coupons_payouts=0,
                    bond_amortization=0,
                    current_cost_one_unit=cost_one_unit,
                    current_cost_asset=cost_one_unit * quantity,
                    total_return=0,
                    holding_days=0,
                    net_profit_pct=0,
                    annualized_return_pct=0,
                )
                db.session.add(new_asset)
                flash('Данные успешно внесены', 'success')

            data_recording_operations_report(
                purchase_date,
                broker_id,
                costs,
                db.session.query(Operations).filter(Operations.operation_type.like(
                    f'покупка {db.session.query(AssetsList).get(asset_type_id).asset_type[:3]}%')).scalar().id,
                f'{asset_name}: {quantity} шт.; ISIN: {isin}, комиссия: {brokerage_fee} руб.'
            )
            db.session.commit()
            updating_data_financial_instruments()
        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in purchase_asset: {str(e)}')

    return render_template('purchase_asset.html')


@app.route('/sale_asset', methods=["POST", "GET"])
def sale_asset():
    if request.method == "POST":
        try:
            broker_id = int(request.form.get('broker_id'))
            asset_type_id = int(request.form.get('asset_type_id'))
            asset_name = request.form.get('asset_name')
            isin = request.form.get('isin')
            sale_date = datetime.strptime(request.form.get('sale_date'), '%Y-%m-%d')
            cost_sell_one_unit = Decimal(request.form.get('cost_sell_one_unit').replace(',', '.'))
            quantity = int(request.form.get('quantity'))
            brokerage_fee = Decimal(request.form.get('brokerage_fee').replace(',', '.'))

            existing_asset = db.session.query(MyAssets).filter(MyAssets.brokerage_account_id == broker_id,
                                                               MyAssets.isin == isin,
                                                               MyAssets.asset_type_id == asset_type_id,
                                                               MyAssets.asset_name == asset_name).first()

            app.logger.info(f'cost_sell_one_unit: {cost_sell_one_unit}, type: {type(cost_sell_one_unit)}')
            app.logger.info(f'quantity: {quantity}, type: {type(quantity)}')

            if not existing_asset:
                flash('Актив не найден', 'error')
                return redirect(url_for('sale_asset'))

            if quantity > existing_asset.quantity:
                flash('Заявленное количество больше чем у вас в портфеле', 'error')
                return redirect(url_for('sale_asset'))

            partial_data_recording_trade_history(broker_id, asset_type_id, asset_name, isin, existing_asset.ticker,
                                                 existing_asset.purchase_date, existing_asset.cost_one_unit,
                                                 quantity, existing_asset.bond_amortization, cost_sell_one_unit,
                                                 sale_date)

            last_record_trade_history = TradeHistory.query.order_by(TradeHistory.id.desc()).first()

            brokerage_account = Brokers.query.get(broker_id)
            costs = cost_sell_one_unit * quantity - brokerage_fee
            brokerage_account.account_balance += costs

            data_recording_operations_report(
                sale_date,
                broker_id,
                costs,
                db.session.query(Operations).filter(Operations.operation_type.like(
                    f'продажа {db.session.query(AssetsList).get(asset_type_id).asset_type[:3]}%')).scalar().id,
                f'{asset_name}: {quantity} шт.; ISIN: {isin}, комиссия: {brokerage_fee} руб.'
            )

            flash(Markup(f"{existing_asset.asset_type.asset_type.capitalize()} - {asset_name}<br>{quantity} шт.<br>"
                         f"ISIN: {isin}<br> успешно проданы"), 'success')

            if existing_asset.quantity == quantity:
                brokerage_fee = existing_asset.brokerage_fee + brokerage_fee
                total_return = (quantity * cost_sell_one_unit - existing_asset.total_purchase_cost - brokerage_fee +
                                existing_asset.dividends_coupons_payouts + existing_asset.bond_amortization)
                net_profit_pct = (total_return / existing_asset.total_purchase_cost) * 100
                annualized_return_pct = (net_profit_pct / last_record_trade_history.holding_days) * 365

                last_record_trade_history.total_purchase_cost = existing_asset.total_purchase_cost
                last_record_trade_history.brokerage_fee = brokerage_fee
                last_record_trade_history.dividends_coupons_payouts = existing_asset.dividends_coupons_payouts
                last_record_trade_history.total_return = total_return
                last_record_trade_history.net_profit_pct = net_profit_pct
                last_record_trade_history.annualized_return_pct = annualized_return_pct

                db.session.delete(existing_asset)

            elif existing_asset.quantity > quantity:
                fin_instr_quantity = existing_asset.quantity - quantity
                fin_instr_total_purchase_cost = Decimal(fin_instr_quantity * existing_asset.cost_one_unit)

                x = Decimal(Decimal(quantity / existing_asset.quantity) * Decimal('100'))
                tr_history_brokerage_fee = (existing_asset.brokerage_fee * x) / Decimal('100')
                tr_history_dividends_coupons_payouts = (existing_asset.dividends_coupons_payouts * x) / Decimal('100')

                existing_asset.quantity = fin_instr_quantity
                existing_asset.total_purchase_cost = fin_instr_total_purchase_cost
                existing_asset.brokerage_fee -= tr_history_brokerage_fee
                existing_asset.dividends_coupons_payouts -= tr_history_dividends_coupons_payouts
                existing_asset.current_cost_one_unit = cost_sell_one_unit

                last_record_trade_history.quantity = quantity
                last_record_trade_history.total_purchase_cost = quantity * existing_asset.cost_one_unit
                last_record_trade_history.brokerage_fee = tr_history_brokerage_fee
                last_record_trade_history.dividends_coupons_payouts = tr_history_dividends_coupons_payouts
                last_record_trade_history.current_cost_one_unit = cost_sell_one_unit
                last_record_trade_history.current_cost_asset = cost_sell_one_unit * quantity
                last_record_trade_history.total_return = (last_record_trade_history.current_cost_asset -
                                                          last_record_trade_history.total_purchase_cost -
                                                          last_record_trade_history.brokerage_fee +
                                                          last_record_trade_history.dividends_coupons_payouts +
                                                          existing_asset.bond_amortization)
                last_record_trade_history.net_profit_pct = ((last_record_trade_history.total_return /
                                                            last_record_trade_history.total_purchase_cost) *
                                                            Decimal('100'))
                last_record_trade_history.annualized_return_pct = (last_record_trade_history.net_profit_pct /
                                                                   last_record_trade_history.holding_days *
                                                                   Decimal('365'))

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in sale_asset: {str(e)}')

        updating_data_financial_instruments()

    return render_template('sale_asset.html')


@app.route('/securities_payments', methods=["POST", "GET"])
def securities_payments():
    if request.method == "POST":
        try:
            operation_id = request.form.get('payment')
            broker_id = int(request.form.get('broker_id'))
            isin = request.form.get('isin')
            asset_name = request.form.get('asset_name')
            payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d')
            payment_amount_one_unit = Decimal(request.form.get('payment_amount'))

            existing_asset = db.session.query(MyAssets).filter(MyAssets.brokerage_account_id == broker_id,
                                                               MyAssets.isin == isin,
                                                               MyAssets.asset_name == asset_name).first()

            if not existing_asset:
                flash('Актив не найден', 'error')
            else:
                brokerage_account = db.session.get(Brokers, broker_id)
                brokerage_account.account_balance += payment_amount_one_unit * existing_asset.quantity

                existing_asset.dividends_coupons_payouts += payment_amount_one_unit * existing_asset.quantity

                operation = OperationsReport(
                    operation_date=payment_date,
                    broker_id=broker_id,
                    amount=payment_amount_one_unit * existing_asset.quantity,
                    operation_type_id=operation_id,
                    note=f'{asset_name}; ISIN: {isin}',
                )
                db.session.add(operation)
                flash('Данные успешно внесены', 'success')
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in securities_payments: {str(e)}')

    return render_template('securities_payments.html')


@app.route('/bond_redemption', methods=["POST", "GET"])
def bond_redemption():
    print(dict(request.form))
    if request.method == "POST":
        try:
            bond_redemption_type_id = int(request.form.get('bond_redemption_type_id'))
            broker_id = int(request.form.get('broker_id'))
            asset_name = request.form.get('asset_name')
            isin = request.form.get('isin')
            bond_redemption_date = datetime.strptime(request.form.get('bond_redemption_date'), '%Y-%m-%d')
            bond_redemption_amount = Decimal(request.form.get('bond_redemption_amount'))

            existing_asset = db.session.query(MyAssets).filter(MyAssets.brokerage_account_id == broker_id,
                                                               MyAssets.isin == isin,
                                                               MyAssets.asset_name == asset_name).first()

            if not existing_asset:
                flash('Облигации не найдены', 'error')
                return redirect(url_for('bond_redemption'))

            operation = OperationsReport(
                operation_date=bond_redemption_date,
                broker_id=broker_id,
                amount=bond_redemption_amount * existing_asset.quantity,
                operation_type_id=bond_redemption_type_id,
                note=f'{asset_name}; ISIN: {isin}',
            )
            db.session.add(operation)

            brokerage_account = db.session.get(Brokers, broker_id)
            brokerage_account.account_balance += bond_redemption_amount * existing_asset.quantity

            if bond_redemption_type_id == 12:
                total_return = (bond_redemption_amount * existing_asset.quantity -
                                existing_asset.total_purchase_cost - existing_asset.brokerage_fee +
                                existing_asset.dividends_coupons_payouts + existing_asset.bond_amortization)
                holding_days = (bond_redemption_date.date() - existing_asset.purchase_date).days + 1
                net_profit_pct = (total_return / existing_asset.total_purchase_cost) * 100
                annualized_return_pct = (net_profit_pct / holding_days) * 365

                data = TradeHistory(
                    brokerage_account_id=existing_asset.brokerage_account_id,
                    asset_type_id=existing_asset.asset_type_id,
                    asset_name=existing_asset.asset_name,
                    isin=existing_asset.isin,
                    ticker=existing_asset.ticker,
                    purchase_date=existing_asset.purchase_date,
                    cost_one_unit=existing_asset.cost_one_unit,
                    quantity=existing_asset.quantity,
                    total_purchase_cost=existing_asset.total_purchase_cost,
                    brokerage_fee=existing_asset.brokerage_fee,
                    dividends_coupons_payouts=existing_asset.dividends_coupons_payouts,
                    bond_amortization=existing_asset.bond_amortization,
                    selling_price_one_unit=bond_redemption_amount,
                    selling_price_asset=bond_redemption_amount * existing_asset.quantity,
                    total_return=total_return,
                    sale_date=bond_redemption_date,
                    holding_days=holding_days,
                    net_profit_pct=net_profit_pct,
                    annualized_return_pct=annualized_return_pct,
                )
                db.session.add(data)
                flash(f'Облигации "{existing_asset.asset_name}" погашены', 'success')
                db.session.delete(existing_asset)
                db.session.commit()

            elif bond_redemption_type_id == 16:
                existing_asset.bond_amortization += bond_redemption_amount * existing_asset.quantity
                existing_asset.current_cost_one_unit -= bond_redemption_amount
                flash('Данные успешно внесены', 'success')

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in bond_redemption: {str(e)}')

    return render_template('bond_redemption.html')


@app.route('/other_operations', methods=["POST", "GET"])
def other_operations():
    if request.method == "POST":
        try:
            broker_id = int(request.form.get('broker_id'))
            operation_type_id = int(request.form.get('operation_type_id'))
            operation_date = datetime.strptime(request.form.get('operation_date'), '%Y-%m-%d')
            amount = Decimal(request.form.get('amount').replace(',', '.'))
            note = request.form.get('note')

            if operation_type_id == 13:
                brokerage_account = db.session.get(Brokers, broker_id)
                brokerage_account.account_balance += amount
                flash(Markup(f'{amount} руб. переведены на счёт:<br>{brokerage_account.broker}'),
                      'success')

                data_recording_operations_report(
                    operation_date,
                    broker_id,
                    amount,
                    db.session.query(Operations).get(operation_type_id).id,
                    note,
                )

            elif operation_type_id == 14:
                brokerage_account = db.session.get(Brokers, broker_id)
                brokerage_account.account_balance -= amount
                flash(Markup(f'{amount} руб. выведены со счёта:<br>{brokerage_account.broker}'),
                      'success')

                data_recording_operations_report(
                    operation_date,
                    broker_id,
                    amount,
                    db.session.query(Operations).get(operation_type_id).id,
                    note,
                )

            elif operation_type_id == 15:
                brokerage_account = db.session.get(Brokers, broker_id)
                brokerage_account.account_balance -= amount
                flash(f'Удержан налог: {amount} руб.', 'success')

                data_recording_operations_report(
                    operation_date,
                    broker_id,
                    amount,
                    db.session.query(Operations).get(operation_type_id).id,
                    note,
                )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in other_operations: {str(e)}')

    return render_template('other_operations.html')


@app.route('/operations_report')
def operations_report():
    """Отчёт по операциям"""

    operations = OperationsReport.query.all()[::-1]
    return render_template('operations_report.html', operations=operations)


@app.route('/trade_history')
def trade_history():
    th_records = TradeHistory.query.order_by(TradeHistory.sale_date.desc()).all()

    return render_template('trade_history.html', th_records=th_records)


@app.route('/update_quotes', methods=["POST", "GET"])
def update_quotes():

    req_db = db.session.query(
        MyAssets.asset_type_id,
        MyAssets.asset_name,
        MyAssets.isin,
        MyAssets.ticker,
        MyAssets.current_cost_one_unit,
    ).order_by(
        MyAssets.asset_type_id
    ).all()

    data = {x[2]: [x[0], x[1], x[3], x[4]] for x in req_db}
    for isin in data:
        data[isin].append(Decimal(update_from_broker_api(data[isin][0], data[isin][2], data[isin][3])))

    # for k, v in data.items():
    #     print(f'{k}, {v}')

    if request.method == "POST":
        try:
            for isin, price in request.form.items():
                asset = MyAssets.query.filter_by(isin=isin).first()
                asset.current_cost_one_unit = price

            db.session.commit()
            updating_data_financial_instruments()
        except Exception as e:
            db.session.rollback()
            flash('Ошибка ввода данных', 'error')
            current_app.logger.error(f'Error in update_quotes: {str(e)}')

    return render_template('update_quotes.html', data=data, AssetsList=AssetsList)


@app.route('/income_report')
def income_report():

    data = db.session.query(
        TradeHistory.sale_date,
        TradeHistory.total_return
    ).order_by(
        TradeHistory.sale_date.desc()
    ).all()

    result = {x[0].year: {} for x in data}
    for dat, amount in data:
        if months_rus[dat.month] not in result[dat.year]:
            result[dat.year][months_rus[dat.month]] = amount
        else:
            result[dat.year][months_rus[dat.month]] += amount

    return render_template('income_report.html', data=result)


@app.errorhandler(404)
def pageNotFount(error):
    return render_template('page404.html', title="Страница не найдена", menu=[])


def shutdown_handler(signum, frame):
    sys.exit(0)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    signal.signal(signal.SIGINT, shutdown_handler)
    app.run(debug=True)





