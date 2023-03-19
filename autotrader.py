# Copyright 2021 Optiver Asia Pacific Pty. Ltd.
#
# This file is part of Ready Trader Go.
#
#     Ready Trader Go is free software: you can redistribute it and/or
#     modify it under the terms of the GNU Affero General Public License
#     as published by the Free Software Foundation, either version 3 of
#     the License, or (at your option) any later version.
#
#     Ready Trader Go is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public
#     License along with Ready Trader Go.  If not, see
#     <https://www.gnu.org/licenses/>.
import asyncio
import itertools

from typing import List

from ready_trader_go import BaseAutoTrader, Instrument, Lifespan, MAXIMUM_ASK, MINIMUM_BID, Side



LOT_SIZE = 10
POSITION_LIMIT = 100
TICK_SIZE_IN_CENTS = 100
MIN_BID_NEAREST_TICK = (MINIMUM_BID + TICK_SIZE_IN_CENTS) // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS
MAX_ASK_NEAREST_TICK = MAXIMUM_ASK // TICK_SIZE_IN_CENTS * TICK_SIZE_IN_CENTS

global_ask_Prices = List[int]
global_ask_Vol = List[int]
global_bid_Prices = List[int]
global_bid_Vol = List[int]

class AutoTrader(BaseAutoTrader):
    """Example Auto-trader.

    When it starts this auto-trader places ten-lot bid and ask orders at the
    current best-bid and best-ask prices respectively. Thereafter, if it has
    a long position (it has bought more lots than it has sold) it reduces its
    bid and ask prices. Conversely, if it has a short position (it has sold
    more lots than it has bought) then it increases its bid and ask prices.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, team_name: str, secret: str):
        global global_ask_Prices
        global global_ask_Vol
        global global_bid_Prices
        global global_bid_Vol
        """Initialise a new instance of the AutoTrader class."""
        super().__init__(loop, team_name, secret)
        self.order_ids = itertools.count(1)
        self.bids = set()
        self.asks = set()
        self.importantorders = {}
        self.futures_orders=set()
        self.ask_id = self.ask_price = self.bid_id = self.bid_price = self.position = 0
        global_ask_Prices = [0,0,0,0,0]
        global_ask_Vol = [0,0,0,0,0]
        global_bid_Prices = [0,0,0,0,0]
        global_bid_Vol = [0,0,0,0,0]

    def on_error_message(self, client_order_id: int, error_message: bytes) -> None:
        """Called when the exchange detects an error.

        If the error pertains to a particular order, then the client_order_id
        will identify that order, otherwise the client_order_id will be zero.
        """
        self.logger.warning("error with order %d: %s", client_order_id, error_message.decode())
        if client_order_id != 0 and (client_order_id in self.bids or client_order_id in self.asks):
            self.on_order_status_message(client_order_id, 0, 0, 0)

    def on_hedge_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your hedge orders is filled.

        The price is the average price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        self.logger.info("received hedge filled for order %d with average price %d and volume %d", client_order_id,
                         price, volume)

    def on_order_book_update_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                                     ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        global global_ask_Prices
        global global_ask_Vol
        global global_bid_Prices
        global global_bid_Vol
        print("itereation ", sequence_number)
    
        #kill any orders that have no shot of being filled/they have lasted for more than 20 updates
        removetheseIDs = list()
        for i in self.bids:
            if(i in self.importantorders):
                if(sequence_number - self.importantorders[i] > 20):
                    removetheseIDs.append(i)
        for i in self.asks:
            if(i in self.importantorders):
                if(sequence_number - self.importantorders[i] > 20):
                    removetheseIDs.append(i)
        for i in removetheseIDs:
            self.send_cancel_order(i)
            self.bids.discard(i)
            self.importantorders.pop(i, None)
        print("done with for loops")
        """Called periodically to report the status of an order book.

        The sequence number can be used to detect missed or out-of-order
        messages. The five best available ask (i.e. sell) and bid (i.e. buy)
        prices are reported along with the volume available at each of those
        price levels.
        """
        self.logger.info("received order book for instrument %d with sequence number %d", instrument,
                         sequence_number)
        #cases: 
        #sell at ETF for higher price, then buy at futures for lower price
        #buy at ETF for lower price, sell at futures for higher price
        #if neither case works, put in buy and sell orders in the ETF market to decrease spread
        midprice = (ask_prices[0] + bid_prices[0])//2
        globalmidprice = (global_ask_Prices[0] + global_bid_Prices[0])//2

        if instrument == Instrument.ETF:
            #figure out if stock price has moved up or down since the last order book update
            goingup=True
            if(midprice< globalmidprice):
                goingup=False

            print("spread is ", ask_prices[0] - bid_prices[0])
            if(ask_prices[0] - bid_prices[0] > 2*TICK_SIZE_IN_CENTS):
                new_bid_price = 0
                new_ask_price = 0
                print("spread is big enough",ask_prices[0] - bid_prices[0])
                if(goingup):
                    #keep the same ask price, increase the bid price from best bidder by 1
                    new_bid_price = bid_prices[0]+TICK_SIZE_IN_CENTS
                    if self.bid_id == 0 and new_bid_price != 0 and self.position < POSITION_LIMIT - 10:
                        self.bid_id = next(self.order_ids)
                        self.bid_price = new_bid_price
                        print("adding bid")
                        self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                        print("sent order")
                        self.importantorders.update({self.bid_id:sequence_number})
                        self.bids.add(self.bid_id)
                else:
                    #keep the same bid price, decrease the ask price by 1
                    new_ask_price = ask_prices[0]-TICK_SIZE_IN_CENTS
                    if self.ask_id == 0 and new_ask_price != 0 and self.position > -POSITION_LIMIT + 10:
                        self.ask_id = next(self.order_ids)
                        self.ask_price = new_ask_price
                        print("adding ask")
                        self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                        self.importantorders.update({self.ask_id:sequence_number})
                        self.asks.add(self.ask_id)
            global_ask_Prices = ask_prices
            global_ask_Vol = ask_volumes
            global_bid_Prices = bid_prices
            global_bid_Vol = bid_volumes
            
        '''
        if instrument == Instrument.FUTURE:
            if(midprice == globalmidprice):
                return
            elif(global_ask_Prices[0] == 0 or global_bid_Prices[0] == 0):
                return
            elif(midprice < globalmidprice):
                #sell on ETF then buy from futures
                new_ask_price = global_ask_Prices[0]-TICK_SIZE_IN_CENTS

                self.ask_id = next(self.order_ids)
                self.ask_price = new_ask_price
                self.send_insert_order(self.ask_id, Side.SELL, new_ask_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.asks.add(self.ask_id)
                #self.futures_orders.add(self.ask_id)
            else:
                new_bid_price = global_bid_Prices[0]+TICK_SIZE_IN_CENTS
                
                self.bid_id = next(self.order_ids)
                self.bid_price = new_bid_price
                self.send_insert_order(self.bid_id, Side.BUY, new_bid_price, LOT_SIZE, Lifespan.GOOD_FOR_DAY)
                self.bids.add(self.bid_id)
        '''

    def on_order_filled_message(self, client_order_id: int, price: int, volume: int) -> None:
        """Called when one of your orders is filled, partially or fully.

        The price is the price at which the order was (partially) filled,
        which may be better than the order's limit price. The volume is
        the number of lots filled at that price.
        """
        global global_ask_Prices
        global global_ask_Vol
        global global_bid_Prices
        global global_bid_Vol
        self.logger.info("received order filled for order %d with price %d and volume %d", client_order_id,
                         price, volume)
        

        if client_order_id in self.bids:
            self.position += volume
            self.send_hedge_order(next(self.order_ids), Side.ASK, MIN_BID_NEAREST_TICK, volume)
            if(self.importantorders.get(client_order_id) != None):
                for i in range(0, 5):
                    self.send_insert_order(next(self.order_ids), Side.ASK, global_ask_Prices[i],global_ask_Vol[i], Lifespan.FILL_AND_KILL)
                    volume-= global_ask_Vol[i]
                    if(volume <=0):
                        break
        elif client_order_id in self.asks:
            self.position -= volume
            self.send_hedge_order(next(self.order_ids), Side.BID, MAX_ASK_NEAREST_TICK, volume)
            if(self.importantorders.get(client_order_id) != None):
                for i in range(0, 5):
                    self.send_insert_order(next(self.order_ids), Side.BID, global_bid_Prices[i],global_bid_Vol[i], Lifespan.FILL_AND_KILL)
                    volume -= global_bid_Vol[i]
                    if(volume <=0):
                        break

    def on_order_status_message(self, client_order_id: int, fill_volume: int, remaining_volume: int,
                                fees: int) -> None:
        """Called when the status of one of your orders changes.

        The fill_volume is the number of lots already traded, remaining_volume
        is the number of lots yet to be traded and fees is the total fees for
        this order. Remember that you pay fees for being a market taker, but
        you receive fees for being a market maker, so fees can be negative.

        If an order is cancelled its remaining volume will be zero.
        """
        self.logger.info("received order status for order %d with fill volume %d remaining %d and fees %d",
                         client_order_id, fill_volume, remaining_volume, fees)
        if remaining_volume == 0:
            if client_order_id == self.bid_id:
                self.bid_id = 0
            elif client_order_id == self.ask_id:
                self.ask_id = 0

            # It could be either a bid or an ask
            print("filled order ",client_order_id)
            self.bids.discard(client_order_id)
            self.asks.discard(client_order_id)
            self.importantorders.pop(client_order_id, None)
            print("done removing item from set and dict")

    def on_trade_ticks_message(self, instrument: int, sequence_number: int, ask_prices: List[int],
                               ask_volumes: List[int], bid_prices: List[int], bid_volumes: List[int]) -> None:
        """Called periodically when there is trading activity on the market.

        The five best ask (i.e. sell) and bid (i.e. buy) prices at which there
        has been trading activity are reported along with the aggregated volume
        traded at each of those price levels.

        If there are less than five prices on a side, then zeros will appear at
        the end of both the prices and volumes arrays.
        """
        self.logger.info("received trade ticks for instrument %d with sequence number %d", instrument,
                         sequence_number)
