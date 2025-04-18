from flask import request, current_app
from datetime import datetime, timedelta, date
from tinkoff.invest import Client
import os
import requests

# from app import app, db
from models import *
from service_files.figi import figi


months_rus = {1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель', 5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
              9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь'}


def transform_number(num: int | float) -> str:
    """
    Функция разбивает число по разрядам,
    если число целое, то убирает нули после запятой.
    """

    if not num:
        return '0'

    if int(num) == float(num):
        return '{0:,}'.format(int(num)).replace(',', ' ')

    num = '{0:,}'.format(round(num, 2)).replace(',', ' ')
    if len(num.split('.')[1]) == 1:
        return num + '0'
    return num


def updating_data_financial_instruments():
    """
    Функция обновляет таблицу базу данных - financial_instruments.
    """

    with current_app.app_context():
        try:
            db.session.query(MyAssets).update(
                {
                    MyAssets.current_cost_asset: MyAssets.quantity * MyAssets.current_cost_one_unit,
                    MyAssets.total_return: (MyAssets.current_cost_asset - MyAssets.total_purchase_cost -
                                           MyAssets.brokerage_fee + MyAssets.dividends_coupons_payouts +
                                           MyAssets.bond_amortization),
                    MyAssets.holding_days: (func.julianday('now') -
                                            func.julianday(MyAssets.purchase_date)).cast(db.Integer) + 1,
                },
                synchronize_session='fetch')
            db.session.commit()

            assets = MyAssets.query.all()
            for asset in assets:
                asset.net_profit_pct = (asset.total_return / asset.total_purchase_cost) * 100
                if asset.ticker in ('-', '', None):
                    ticker = get_ticker(asset.isin)
                    if ticker:
                        asset.ticker = ticker
            db.session.commit()

            db.session.query(MyAssets).update(
                {MyAssets.annualized_return_pct: (MyAssets.net_profit_pct / MyAssets.holding_days) * 365},
                synchronize_session='fetch'
            )
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка при обновлении активов: {str(e)}")


def update_from_broker_api(asset_type_id, ticker, current_cost_one_unit):
    """
    Функция получает котировки ценных бумаг с Московской биржи.
    """

    try:
        if asset_type_id in (1, 4):
            url = f'https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json'
            params = {'iss.meta': 'off'}
            data = requests.get(url, params=params).json()
            for item in data['securities']['data']:
                if item[1] in ('TQBR', 'TQTF'):
                    return item[22] if item[22] else item[3]

        if asset_type_id == 2:
            url = f'https://iss.moex.com/iss/engines/stock/markets/bonds/securities/{ticker}.json'
            params = {'iss.meta': 'off'}
            data = requests.get(url, params=params).json()
            for item in data['securities']['data']:
                if item[1] in ('TQCB', 'TQOB'):
                    return item[3] * item[10] / 100 if item[3] else current_cost_one_unit

        if asset_type_id == 3:
            url = 'https://www.cbr-xml-daily.ru/daily_json.js'
            data = requests.get(url).json()
            price = data['Valute'][ticker]['Value']
            return price if price else current_cost_one_unit

    except Exception as e:
        print(f'Ошибка при попытке обновления котировок {e}')

    return current_cost_one_unit


def get_ticker(isin):
    """
    Функция получает значение ticker ценной буиаги по её ISIN.
    """

    try:
        url = f'https://iss.moex.com/iss/securities.json?q={isin}'
        data = requests.get(url).json()
        ticker = data['securities']['data'][0][0]
        return ticker
    except Exception as e:
        print(f'Ошибка при получении ticker {e}')
