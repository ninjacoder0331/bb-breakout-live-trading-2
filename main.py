import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from ta.volatility import BollingerBands
from ta.trend import SMAIndicator
import time
import os
from datetime import datetime
import requests
import json
import asyncio
import schedule
import ntplib
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

entry_price = 0

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

async def check_market_time():
    try:
        # Get time from NTP server
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request('pool.ntp.org')
        # Convert NTP time to datetime and set timezone to ET
        current_time = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
    except Exception as e:
        print(f"Error getting NTP time: {e}")
        # Fallback to local time if NTP fails
        current_time = datetime.now(ZoneInfo("America/New_York"))

    print("current_time: ", current_time)
    
    # Check if it's a weekday (0 = Monday, 6 = Sunday)
    if current_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Create time objects for market open and close
    market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Check if current time is within market hours
    is_market_open = market_open <= current_time <= market_close
    return is_market_open


async def current_time():
    try :
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request('pool.ntp.org')
        currentTime = datetime.fromtimestamp(response.tx_time, ZoneInfo("America/New_York"))
        return currentTime.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception as e:
        print(f"Error getting NTP time: {e}")
        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")

async def get_database(collection_name: str):
    try:
        MONGODB_URL = os.getenv("MONGODB_URL")
        client = AsyncIOMotorClient(MONGODB_URL)
        
        # Get list of all databases
        dbs = await client.list_database_names()
        
        # Check if optionsTrading database exists
        if "tradingDB" not in dbs:
            print("Creating tradingDB database...")
            # Create database by inserting a document
            db = client.get_database("tradingDB")
            await db.create_collection("traders")  # Create traders collection
            print("Created tradingDB database with collections")
        
        # Get database and collection
        db = client.get_database("tradingDB")
        
        # Check if collection exists
        collections = await db.list_collection_names()

        if "analyst" not in collections:
            print("Creating analyst collection with initial data...")
            analyst_collection = db.get_collection("analyst")
            
            # Initial analysts data
            initial_analysts = [{
                    "name": "John",
                    "type": "analyst1"
                },
                {
                    "name": "WiseGuy",
                    "type": "analyst2"
                },
                {
                    "name": "Tommy",
                    "type": "analyst3"
                },
                {
                    "name": "Johnny",
                    "type": "analyst4"
                }]
            await analyst_collection.insert_many(initial_analysts)
            print("Created analyst collection with all initial data")

        if "startStopSettings" not in collections:
            print("Creating startStopSettings collection with initial data...")
            start_stop_collection = db.get_collection("startStopSettings")
            
            # Initial start/stop settings
            initial_settings = {
                "stockStart": False,
                "optionsStart": False
            }
            await start_stop_collection.insert_one(initial_settings)
            print("Created startStopSettings collection with initial data")
        
        collection = db.get_collection(collection_name)
        print("collection")
        return collection
    
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        return None

async def create_order(symbol, quantity):
    try:
        stock_history_collection = await get_database("stockHistory")
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        stock_amount = settings["stockAmount"]
        formatted_time = await current_time() 
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")

        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": symbol,
            "qty": stock_amount,
            "side": "buy"
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)
        # print("response1", response.json())
        tradingId = response.json()["id"]
        # print("tradingId", tradingId)

        if tradingId != "":
            await asyncio.sleep(2)
            url2 = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=UVIX"
            response2 = requests.get(url2, headers=headers)

            for order in response2.json():
                if order["id"] == tradingId:
                    price = order["filled_avg_price"]
                    buy_quantity = order["filled_qty"]
                    entrytimestamp = order["filled_at"]
                    
                    history_data = {
                        "symbol": symbol,
                        "quantity": buy_quantity,
                        "entryPrice": price,
                        "exitPrice": 0,
                        "type": "BUY",
                        "tradingId": tradingId,
                        "tradingType" : "auto",
                        "status": "open",
                        "entrytimestamp": entrytimestamp,
                        "exitTimestamp": None
                    }

                    await stock_history_collection.insert_one(history_data)
                    break;
                    
        logging.info(f"[{datetime.now()}] Buy order created for symbol: {symbol}, quantity: {quantity}")
        return entry_price
    except Exception as e:
        return None

async def create_sell_order(symbol, quantity):
    try:
        global entry_price

        entry_price = 0
        # Save to stockHistory collection
        stock_history_collection = await get_database("stockHistory")
        stock_history = await stock_history_collection.find_one({"symbol": symbol, "status": "open" , "tradingType" : "auto"})
        
        settings_collection = await get_database("settings")
        settings = await settings_collection.find_one({})
        stock_amount = settings["stockAmount"]
        
        if not stock_history:
            return {"message": "No open position found for this symbol", "status": "not_found"}

        tradingId = stock_history["tradingId"]

        # Configure Alpaca credentials
        alpaca_api = os.getenv("ALPACA_API_KEY")
        alpaca_secret = os.getenv("ALPACA_SECRET_KEY")
        url = "https://paper-api.alpaca.markets/v2/orders"

        payload = {
            "type": "market",
            "time_in_force": "day",
            "symbol": stock_history["symbol"],
            "qty": stock_amount,
            "side": "sell"
        }
        # print("payload", payload)
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": alpaca_api,
            "APCA-API-SECRET-KEY": alpaca_secret
        }

        response = requests.post(url, json=payload, headers=headers)
        tradingId = response.json()["id"]
        # print("response", response.json())
        # print("tradingId", tradingId)
        
        if response.status_code == 200:
            await asyncio.sleep(3)
            url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=UVIX"
            # url = "https://paper-api.alpaca.markets/v2/orders?status=all&symbols=" + stock_history["symbol"]

            # print("url", url)
            response = requests.get(url, headers=headers)
            price = 0
            for order in response.json():
                if order["id"] == tradingId:
                    price = order["filled_avg_price"]
                    
                    exitTimestamp = order["filled_at"] 
                    # print("----------------------------", price)
                    print("sell order is excuted" , price)
                    await stock_history_collection.update_one(
                        {"symbol": symbol, "status": "open" , "tradingType" : "auto" },
                        {"$set": {"status": "closed" , "exitPrice" : price , "exitTimestamp" : exitTimestamp}}
                    )
                    return {"message": "Sell order processed successfully", "status": "success", "exitPrice": price}
                break;
        
        return {"message": "Failed to process sell order", "status": "error"}
        
    except Exception as e:
        return None

class BBStrategy:
    def __init__(self, bb_length=20, bb_mult=1.5, slope_lookback=5, tp_perc=0.02, sl_perc=0.003):
        self.bb_length = bb_length
        self.bb_mult = bb_mult
        self.slope_lookback = slope_lookback
        self.tp_perc = tp_perc
        self.sl_perc = sl_perc
        self.current_position = 0
        self.entry_price = 0
        self.stop_loss = 0
        self.take_profit = 0
        
    def calculate_indicators(self, df):
        # Calculate Bollinger Bands
        bb = BollingerBands(close=df['mid_price'], window=self.bb_length, window_dev=self.bb_mult)
        df['bb_basis'] = bb.bollinger_mavg()
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        
        # Calculate slope
        df['slope'] = df['bb_basis'] - df['bb_basis'].shift(self.slope_lookback)
        df['slope_up'] = df['slope'] > 0
        
        return df
    
    def generate_signals(self, df):
        # Entry condition: Price above upper band and positive slope
        df['entry'] = (df['mid_price'] > df['bb_upper']) & df['slope_up']
        
        # Calculate stop loss and take profit levels
        df['stop_loss'] = df['mid_price'] * (1 - self.sl_perc / 100)
        df['take_profit'] = df['mid_price'] * (1 + self.tp_perc / 100)
        
        return df
    
    def check_signals(self, df):
        """Check for trading signals in the latest data"""
        latest_data = df.iloc[-1]

        bid_price = float(latest_data['mid_price'])
        
        # Check for entry signal
        if latest_data['entry'] and self.current_position == 0:
            self.current_position = 1
            self.entry_price = float(latest_data['mid_price'])  # Ensure it's a float
            self.stop_loss = float(latest_data['stop_loss'])    # Ensure it's a float
            self.take_profit = float(latest_data['take_profit'])  # Ensure it's a float
            return "BUY"
        
        # Check for exit conditions
        if self.current_position == 1:
            global entry_price
            entry_float_price = float(entry_price)
            print("================entry_price=========", entry_float_price)
            stop_loss = entry_float_price * (1 - self.sl_perc / 100)
            take_profit = entry_float_price * (1 + self.tp_perc / 100)
            if bid_price <= stop_loss:
                self.current_position = 0
                return "SELL_STOP_LOSS"
            elif bid_price >= take_profit:
                self.current_position = 0
                return "SELL_TAKE_PROFIT"
            else:
                return "HOLD"
        
        return "HOLD"

class LiveTrading:
    def __init__(self, data_file, params):
        self.data_file = data_file
        self.params = params
        self.strategy = BBStrategy(
            bb_length=params.get('bb_length', 20),
            bb_mult=params.get('bb_mult', 1.5),
            slope_lookback=params.get('slope_lookback', 5),
            tp_perc=params.get('take_profit_percent', 0.02),
            sl_perc=params.get('stop_loss_percent', 0.003)
        )
        self.trades = []
    
    async def fetch_market_data(self):
        """Fetch market data from API"""
        try:
            url = "https://data.alpaca.markets/v2/stocks/quotes/latest?symbols=UVIX&feed=iex"
            url2 = "https://data.alpaca.markets/v2/stocks/bars/latest?symbols=UVIX&feed=iex"


            headers = {
                "accept": "application/json",
                "APCA-API-KEY-ID": ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
            }

            print("Fetching data from Alpaca...")
            response = requests.get(url, headers=headers)
            response2 = requests.get(url2, headers=headers)
            quotes = response.json()["quotes"]["UVIX"]
            quotes2 = response2.json()["bars"]["UVIX"]
            print("Received quotes:", quotes)
            print("Received quotes2:", quotes2)

            bid_price = quotes["bp"]
            ask_price = quotes["ap"]
            
            # If bid price is 0, try to get the previous bid price from the CSV
            if bid_price == 0:
            
                df_existing = pd.read_csv('your_data.csv')
                if not df_existing.empty:
                    # Get the last non-zero bid price
                    last_valid_bid = df_existing[df_existing['bid_price'] > 0]['bid_price'].iloc[-1]
                    bid_price = last_valid_bid
                    print(f"Using previous bid price: {bid_price}")
                else:
                    bid_price = ask_price - 0.5
            
            if ask_price == 0:
            
                df_existing = pd.read_csv('your_data.csv')
                if not df_existing.empty:
                    last_valid_ask = df_existing[df_existing['ask_price'] > 0]['ask_price'].iloc[-1]
                    ask_price = last_valid_ask
                    print(f"Using previous ask price: {ask_price}")
                else:
                    ask_price = bid_price + 0.5
                
            mid_price = (bid_price + ask_price) / 2
            utctime = quotes["t"]
            history_time = await current_time()

            # Create new data row from quotes
            new_data = {
                "bid_price": bid_price,
                "ask_price": ask_price,
                "mid_price": mid_price,
                "utctime": utctime,
                "history_time": history_time
            }

            # Read existing data and keep only last 74 lines
            try:
                df_existing = pd.read_csv('your_data.csv')
                if len(df_existing) >= 74:
                    df_existing = df_existing.tail(74)
                
            except FileNotFoundError:
                df_existing = pd.DataFrame()

            # Append new data
            df_new = pd.DataFrame([new_data])
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            
            # Save the combined data
            df_combined.to_csv('your_data.csv', index=False)
            print("Updated CSV with new data, maintaining 75 lines maximum")

            # save data to the analyst collection
            try:                                  
                df_my_data = pd.read_csv('analyst.csv')
            except FileNotFoundError:
                # Create a new DataFrame with the same columns as new_data
                df_my_data = pd.DataFrame(columns=new_data.keys())
            
            # Convert new_data to DataFrame and concatenate
            new_df = pd.DataFrame([new_data])
            df_my_data = pd.concat([df_my_data, new_df], ignore_index=True)
            df_my_data.to_csv('analyst.csv', index=False)

            # save bar data to the bar db

            close_price = quotes2["c"]
            high_price = quotes2["h"]
            low_price = quotes2["l"]
            open_price = quotes2["o"]
            volume = quotes2["v"]
            utctime = quotes2["t"]

            bar_data = {
                "close_price": close_price,
                "high_price": high_price,
                "low_price": low_price,
                "open_price": open_price,
                "volume": volume,
                "utctime": utctime,
                "history_time": history_time
            }

            try:                                  
                df_my_data = pd.read_csv('bar_data.csv')
            except FileNotFoundError:
                # Create a new DataFrame with the same columns as new_data
                df_my_data = pd.DataFrame(columns=bar_data.keys())


            new_data2 = pd.DataFrame([bar_data])
            df_new_data = pd.concat([df_my_data, new_data2], ignore_index=True)
            df_new_data.to_csv('bar_data.csv', index=False)
            
            

            return new_data
                
        except Exception as e:
            print(f"Error fetching market data: {e}")
            return None

    
    async def run(self):
        while True:
            try:
                start_time = time.time()
                print("Checking market time...")
                is_market_open = await check_market_time()
                print(datetime.now())
                if is_market_open:
                    print("Market is closed. Skipping position checks.")
                else: 
                    print("Market is open")

                    # Fetch and update data
                    new_data = await self.fetch_market_data()
                    
                    # Load and process data
                    df = pd.read_csv(self.data_file)
                    df['utctime'] = pd.to_datetime(df['utctime'])
                    df.set_index('utctime', inplace=True)
                    
                    # Calculate indicators
                    df = self.strategy.calculate_indicators(df)
                    df = self.strategy.generate_signals(df)
                    
                    # Check for trading signals
                    signal = self.strategy.check_signals(df)
                    
                    # Process the signal
                    if signal != "HOLD":
                        symbol = "UVIX"
                        quantity = 1
                        
                        if signal == "BUY":
                            await create_order(symbol, quantity)
                            global entry_price
                            entry_price = new_data["mid_price"]
                        elif signal == "SELL_STOP_LOSS":
                            await create_sell_order(symbol, quantity)
                        elif signal == "SELL_TAKE_PROFIT":
                            await create_sell_order(symbol, quantity)
                        print(f"\nTrade Signal: {signal}")
                    
                    # Calculate elapsed time
                    elapsed_time = time.time() - start_time
                    print(f"Cycle completed in {elapsed_time:.2f} seconds")
                
                # Wait for the remaining time to complete 1 minute
                if elapsed_time < 60:
                    await asyncio.sleep(60 - elapsed_time)
                else:
                    print("Warning: Cycle took longer than 1 minute!")
                
            except Exception as e:
                print(f"Error in live trading: {e}")
                await asyncio.sleep(60)

if __name__ == "__main__":
    print("Starting live trading bot...")
    
    async def main():
        # Trading parameters
        params = {
            'bb_length': 20,
            'bb_mult': 1.5,
            'slope_lookback': 5,
            'take_profit_percent': 0.02,  # 2%
            'stop_loss_percent': 0.003     # 0.3%
        }
        
        # Initialize live trading
        live_trader = LiveTrading('your_data.csv', params)
        
        # Start live trading
        print("Starting live trading111...")
        await live_trader.run()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping the script...")