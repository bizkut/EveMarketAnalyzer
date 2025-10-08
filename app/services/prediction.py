import pandas as pd
from sklearn.linear_model import LinearRegression
import numpy as np

def prepare_features(df: pd.DataFrame):
    """
    Prepares features for the prediction model from historical data.
    """
    df = df.sort_values('date').reset_index(drop=True)

    # Create lagged features
    df['avg_price_lag1'] = df['average'].shift(1)
    df['volume_lag1'] = df['volume'].shift(1)

    # Rolling window features
    df['avg_price_7d'] = df['average'].rolling(window=7).mean()
    df['avg_price_30d'] = df['average'].rolling(window=30).mean()
    df['volume_7d'] = df['volume'].rolling(window=7).mean()
    df['volatility_7d'] = df['average'].rolling(window=7).std()

    # Trend feature
    if len(df) > 1:
        price_slope = np.polyfit(range(len(df)), df['average'], 1)[0]
        df['trend_direction'] = 1 if price_slope > 0 else -1 if price_slope < 0 else 0
    else:
        df['trend_direction'] = 0

    # Target variables
    df['next_day_lowest'] = df['lowest'].shift(-1)
    df['next_day_highest'] = df['highest'].shift(-1)

    df = df.dropna()

    return df

def train_and_predict(df: pd.DataFrame):
    """
    Trains a linear regression model and predicts the next day's prices.
    """
    if len(df) < 30: # Need enough data to create features
        return {"predicted_buy_price": None, "predicted_sell_price": None}

    featured_df = prepare_features(df)

    if featured_df.empty:
        return {"predicted_buy_price": None, "predicted_sell_price": None}

    # Define features and targets
    features = [
        'avg_price_7d', 'avg_price_30d', 'volume_7d',
        'volatility_7d', 'trend_direction', 'avg_price_lag1', 'volume_lag1'
    ]

    X = featured_df[features]
    y_buy = featured_df['next_day_lowest']
    y_sell = featured_df['next_day_highest']

    # Train buy price prediction model
    buy_model = LinearRegression()
    buy_model.fit(X, y_buy)

    # Train sell price prediction model
    sell_model = LinearRegression()
    sell_model.fit(X, y_sell)

    # Prepare the last row of data for prediction
    last_features = featured_df[features].iloc[-1:].values

    # Predict
    predicted_buy = buy_model.predict(last_features)[0]
    predicted_sell = sell_model.predict(last_features)[0]

    return {
        "predicted_buy_price": predicted_buy,
        "predicted_sell_price": predicted_sell
    }