import argparse
import requests
import socket
import pandas as pd
import configparser

class Server:
    # Store data as dictionary mapping ticker to dataframe containing
    #   date, price, signal, pnl columns.
    # Could be done w/out pandas, but since not specified just makes life a little easier
    # TODO: maybe use MultiIndex instead, but storing independently means they can also be updated independently
    data = {}
    # Alpha Vantage Historical API url
    AV_URL = 'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={ticker}&interval={interval}min&outputsize=full&apikey={token}'
    # Finnhub real-time quote API url
    FH_URL = 'https://finnhub.io/api/v1/quote?symbol={ticker}&token={token}'
    def __init__(self, tickers, port, interval, reload, av_token, fh_token):
        self.tickers = set(tickers)
        self.port = port
        self.interval = interval
        self.reload = reload
        # Calculate number of observations to create 24 hour rolling window
        # Assume 24 trading hours as defined from our data rather than literally 24 hours
        self.WINDOW_SIZE = 24 * int(60 / interval)
        self._AV_TOKEN = av_token
        self._FH_TOKEN = fh_token

        self.load_all()
        self.output_csv()


    def load_all(self):
        for ticker in self.tickers:
            if self.reload:
                # self.load_historical_reload(ticker)
                print("Unimplemented")
                return 1
            else:
                self.load_historical_alpha(ticker)
        return 0

    
    def output_csv(self):
        for ticker in self.tickers:
            df = self.data[ticker]
            df[['price','signal', 'pnl']].to_csv('{}_result.csv'.format(ticker.lower()))
            df[['price']].to_csv('{}_price.csv'.format(ticker.lower()))


    def load_historical_reload(self, ticker):
        # Not much info given about file format, so not implemented for now
        # Essentially the same as alpha fn after extracting the price data
        pass


    def _compute_position(self, row):
        # Compute the position based on given formula
        if row['price'] > row['s_avg'] + row['sigma_t']:
            return 1
        elif row['price'] < row['s_avg'] - row['sigma_t']:
            return -1

    def load_historical_alpha(self, ticker):
        # Use Alpha Vantage API to load historical data for ticker
        # Assume extended data not required
        url = self.AV_URL.format(ticker=ticker, interval=self.interval, token=self._AV_TOKEN)
        r = requests.get(url).json()
        if 'Error Message' in r:
            return "Invalid Ticker"
        # Create DF, use closing price, sort in increasing order
        df = pd.DataFrame.from_dict(r['Time Series ({}min)'.format(self.interval)], orient='index').drop(['1. open', '2. high','3. low','5. volume'], axis=1)
        df.index = pd.to_datetime(df.index).rename('datetime')
        df = df.rename(columns={'4. close': 'price'}).sort_index()
        df['price'] = df['price'].astype(float)

        rolling_window = df.rolling(self.WINDOW_SIZE)
        S_avg = rolling_window.mean()
        Sigma_t = rolling_window.std()
        # We use the previous day's (t) data to calculate the signal for t+1
        df['s_avg'] = S_avg
        df['sigma_t'] = Sigma_t
        df['signal'] = df.apply(self._compute_position, axis=1)
        # If S(t) within Sigma(t) of S_avg(t) we carry forward the previous signal
        df['signal'] = df['signal'].ffill()
        # Use signal computed at time t to inform position at time t+1 and use this for PnL calculation
        df['signal'] = df['signal'].shift(1)
        df['prev_price'] = df['price'].shift(1)
        df['pnl'] = df['signal'] * (df['price'] - df['prev_price'])
        # TODO: Not required but including for testing, can remove later
        df['cumul_pnl'] = df['pnl'].cumsum()
        # Update data
        self.data[ticker] = df
        return 0


    def _update_stock(self, ticker):
        url = self.FH_URL.format(ticker=ticker, token=self._FH_TOKEN)
        quote = requests.get(url).json()
        curr_price = quote['c']
        ts = pd.to_datetime(quote['t'], unit='s')
        df = self.data[ticker]
        # Get prev 24 hours of data and compute signal and pnl
        prev_day = df.iloc[-self.WINDOW_SIZE:]
        s_avg = prev_day['price'].mean()
        sigma_t = prev_day['price'].std()
        prev_row = prev_day.iloc[-1]
        signal = self._compute_position(prev_row)
        if not signal:
            # Carry forward signal
            signal = prev_row.signal
        pnl = signal * (curr_price - prev_row.price)
        cumul_pnl = prev_row.cumul_pnl + pnl
        new_row = {'price':curr_price, 's_avg': s_avg, 'sigma_t': sigma_t, 'signal': signal, 'prev_price':prev_row.price, 'pnl': pnl, 'cumul_pnl': cumul_pnl}
        self.data[ticker] = df.append(pd.Series(new_row, name=ts))

    
    def _get_filtered(self, ticker, time):
        # Return data for ticker at or after time
        df = self.data[ticker]
        return df[df.index >= time]

    def get_prices(time):
        # Return latest price available as of time for each ticker
        result = {}
        for ticker in self.tickers:
            df = self._get_filtered(ticker, time)
            price = 'No Data'
            if len(df) > 0:
                price = df.iloc[0].price
            result[ticker] = price
        return result

    
    def get_signals(time):
        result = {}
        for ticker in self.tickers:
            df = self._get_filtered(ticker, time)
            signal = 'No Data'
            if len(df) > 0:
                signal = df.iloc[0].signal
            result[ticker] = signal
        return result


    def delete(ticker):
        # TODO: handle update threads
        if ticker not in self.tickers:
            return "Invalid Ticker"
        removed = self.data.pop(ticker, None)
        self.tickers.remove(ticker)


    def add(ticker):
        # TODO: handle update threads
        self.tickers.add(ticker)
        return self.load_historical_alpha(ticker)


    def reset():
        self.temp = self.data
        self.data = {}
        result = self.load_all()
        if result == 1:
            self.data = self.temp
            return 1
        return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--tickers', default=['AAPL'], nargs='*', help='Tickers to track (max 3)')
    parser.add_argument('-p', '--port', default='8000', help='Port to bind server to')
    parser.add_argument('-r', '--reload', help='A reload file to load historical data from')
    parser.add_argument('-m', '--minutes', default=5, type=int, choices=[5, 15, 30, 60], help='Data update interval in minutes (5, 15, 30, 60)')

    args = parser.parse_args()
    print(args.tickers)
    print(args.reload)
    print(args.minutes)
    if len(args.tickers) > 3:
        print('error: cannot specify more than 3 tickers')
    
    config = configparser.ConfigParser()
    config.read('config.txt')
    tokens = config['API Tokens']
    print(tokens['av_token'], tokens['fh_token'])

    server = Server(args.tickers, args.port, args.minutes, args.reload,
            tokens['av_token'], tokens['fh_token'])
    