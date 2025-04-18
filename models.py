from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric, func
from sqlalchemy.orm import joinedload


db = SQLAlchemy()  # инициализация SQLAlchemy


class MyAssets(db.Model):
    __tablename__ = 'financial_instruments'

    id = db.Column(db.Integer, primary_key=True)
    brokerage_account_id = db.Column(db.Integer, db.ForeignKey('brokers.id'))  # брокер
    asset_type_id = db.Column(db.Integer, db.ForeignKey('assets_list.id'))  # тип актива
    asset_name = db.Column(db.String(100))  # наименование актива (эмитент или валюта и т.д.)
    isin = db.Column(db.String(100))  # ISIN
    ticker = db.Column(db.String(100))  # краткое название в биржевой информации
    purchase_date = db.Column(db.Date)  # дата покупки
    cost_one_unit = db.Column(Numeric(precision=50, scale=2))  # стоимость 1 ед.
    quantity = db.Column(db.Integer)  # количество приобретаемого актива
    total_purchase_cost = db.Column(Numeric(precision=50, scale=2))  # общая стоимость покупки
    brokerage_fee = db.Column(Numeric(precision=50, scale=2))  # комиссия брокера
    dividends_coupons_payouts = db.Column(Numeric(precision=50, scale=2))  # выплаты (диведенды, купоны и т.д.)
    bond_amortization = db.Column(Numeric(precision=50, scale=2))  # амортизация (для облигаций)
    current_cost_one_unit = db.Column(Numeric(precision=50, scale=2))  # текущая стоимость актива 1 ед.
    current_cost_asset = db.Column(Numeric(precision=50, scale=2))  # общая текущая стоимость актива
    total_return = db.Column(Numeric(precision=50, scale=2))  # совокупный доход
    holding_days = db.Column(db.Integer)  # количество дней пользования активом
    net_profit_pct = db.Column(Numeric(precision=50, scale=2))  # чистый доход %
    annualized_return_pct = db.Column(Numeric(precision=50, scale=2))  # годовой доход %

    asset_type = db.relationship('AssetsList', backref='financial_instruments_asset_types')
    broker = db.relationship('Brokers', backref='financial_instruments_brokers')


class AssetsList(db.Model):
    __tablename__ = 'assets_list'

    id = db.Column(db.Integer, primary_key=True)
    asset_type = db.Column(db.String(100))


class Brokers(db.Model):
    __tablename__ = 'brokers'

    id = db.Column(db.Integer, primary_key=True)
    broker = db.Column(db.String(100))
    account_balance = db.Column(Numeric(precision=50, scale=2))


class OperationsReport(db.Model):
    __tablename__ = 'operations_report'

    id = db.Column(db.Integer, primary_key=True)
    operation_date = db.Column(db.Date)
    broker_id = db.Column(db.Integer, db.ForeignKey('brokers.id'))
    amount = db.Column(Numeric(precision=50, scale=2))
    operation_type_id = db.Column(db.Integer, db.ForeignKey('operations.id'))
    note = db.Column(db.Text)

    broker = db.relationship('Brokers', backref='operations_report_brokers')
    operation_type = db.relationship('Operations', backref='operations_report_operations')


class Operations(db.Model):
    __tablename__ = 'operations'

    id = db.Column(db.Integer, primary_key=True)
    operation_type = db.Column(db.String(100))
    category_type = db.Column(db.String(100))


class TradeHistory(db.Model):
    """
    Таблица "История сделок"
    """

    __tablename__ = 'trade_history'

    id = db.Column(db.Integer, primary_key=True)
    brokerage_account_id = db.Column(db.Integer, db.ForeignKey('brokers.id'))  # брокер
    asset_type_id = db.Column(db.Integer, db.ForeignKey('assets_list.id'))  # тип актива
    asset_name = db.Column(db.String(100))  # наименование актива (эмитент или валюта и т.д.)
    isin = db.Column(db.String(100))  # ISIN
    ticker = db.Column(db.String(100))  # краткое название в биржевой информации
    purchase_date = db.Column(db.Date)  # дата покупки
    cost_one_unit = db.Column(Numeric(precision=50, scale=2))  # стоимость 1 ед.
    quantity = db.Column(db.Integer)  # количество приобретаемого актива
    total_purchase_cost = db.Column(Numeric(precision=50, scale=2))  # общая стоимость покупки
    brokerage_fee = db.Column(Numeric(precision=50, scale=2))  # комиссия брокера
    dividends_coupons_payouts = db.Column(Numeric(precision=50, scale=2))  # выплаты (диведенды, купоны и т.д.)
    bond_amortization = db.Column(Numeric(precision=50, scale=2))  # амортизация (для облигаций)
    selling_price_one_unit = db.Column(Numeric(precision=50, scale=2))  # цена продажи актива 1 ед.
    selling_price_asset = db.Column(Numeric(precision=50, scale=2))  # общая цена продажи актива
    total_return = db.Column(Numeric(precision=50, scale=2))  # совокупный доход
    sale_date = db.Column(db.Date)   # дата продажи
    holding_days = db.Column(db.Integer)  # количество дней пользования активом
    net_profit_pct = db.Column(Numeric(precision=50, scale=2))  # чистый доход %
    annualized_return_pct = db.Column(Numeric(precision=50, scale=2))  # годовой доход %

    asset_type = db.relationship('AssetsList', backref='trade_history_asset_types')
    broker = db.relationship('Brokers', backref='trade_history_brokers')
