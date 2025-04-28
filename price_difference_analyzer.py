import pandas as pd
import matplotlib.pyplot as plt

# Read the CSV file
df = pd.read_csv('your_data.csv')

# Calculate the difference between ask_price and bid_price (spread)
df['spread'] = df['ask_price'] - df['bid_price']

# Print the results
print("\nPrice Spread Analysis:")
print("=" * 50)
for index, row in df.iterrows():
    print(f"Time: {row['history_time']}")
    print(f"Bid Price: {row['bid_price']:.2f}")
    print(f"Ask Price: {row['ask_price']:.2f}")
    print(f"Spread: {row['spread']:.2f}")
    print("-" * 50)

# Calculate and print summary statistics
print("\nSpread Statistics:")
print("=" * 50)
print(f"Minimum Spread: {df['spread'].min():.2f}")
print(f"Maximum Spread: {df['spread'].max():.2f}")
print(f"Average Spread: {df['spread'].mean():.2f}")
print(f"Median Spread: {df['spread'].median():.2f}")

# Create a simple visualization
plt.figure(figsize=(12, 6))
plt.plot(df['history_time'], df['spread'], marker='o', linestyle='-')
plt.title('Bid-Ask Spread Over Time')
plt.xlabel('Time')
plt.ylabel('Spread')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show() 