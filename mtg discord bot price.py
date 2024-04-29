import discord
from discord.ext import commands, tasks
import requests
import sqlite3
from datetime import datetime, timedelta

# The token comes from the dev part in discord.
BOT_TOKEN = "Token_ID"

# BASE_URL is the URL for the API lookup.
BASE_URL = "https://api.scryfall.com"

# Connect to SQLite database
conn = sqlite3.connect('card_prices.db')
c = conn.cursor()

# Create card_prices table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS card_prices
             (card_name TEXT, price REAL, date_added TEXT, user_id INTEGER)''')

# Commit changes and close connection
conn.commit()
conn.close()

# Create a bot instance using commands.Bot
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Function to add price to database
def add_price_to_db(card_name, price, user_id):
    conn = sqlite3.connect('card_prices.db')
    c = conn.cursor()
    c.execute("INSERT INTO card_prices VALUES (?, ?, ?, ?)",
              (card_name, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

# Function to check for price change and notify
async def check_price_change():
    try:
        conn = sqlite3.connect('card_prices.db')
        c = conn.cursor()
        c.execute("SELECT card_name, price, user_id FROM card_prices GROUP BY card_name, user_id")
        rows = c.fetchall()
        conn.close()

        for row in rows:
            card_name, current_price, user_id = row
            url = f'{BASE_URL}/cards/named?fuzzy={card_name}'
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                new_price = data.get('prices', {}).get('usd')
                if new_price is not None and new_price != current_price:
                    print(f'Price of "{card_name}" has changed! New price: {new_price}')
                    user = bot.get_user(user_id)
                    if user:
                        await user.send(f'Price of "{card_name}" has changed! New price: {new_price}')
            else:
                print(f'Error fetching data for "{card_name}"')
                # Log the error or send a message to the user informing about the error
    except Exception as e:
        print(f'Error in check_price_change: {e}')
        # Log the error or send a message to the user informing about the error

# Background task to check for price changes periodically
@tasks.loop(hours=24)  # Adjust the interval as needed (e.g., check every 24 hours)
async def price_change_check():
    await check_price_change()


# Background task to delete old entries from the database
@tasks.loop(hours=24)  # Run once a day to delete old entries
async def delete_old_entries():
    try:
        conn = sqlite3.connect('card_prices.db')
        c = conn.cursor()
        c.execute("DELETE FROM card_prices WHERE date_added < ?", (datetime.now() - timedelta(days=30),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'Error in delete_old_entries: {e}')
        # Log the error or send a message to the user informing about the error


# Start the background tasks when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    price_change_check.start()
    delete_old_entries.start()


# Define a command to get the price, image, and text of a card
@bot.command()
async def card(ctx, card_number: str, set_code: str):
    try:
        url = f'{BASE_URL}/cards/{set_code}/{card_number}'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            card_name = data.get('name')
            price = data.get('prices', {}).get('usd')
            image_url = data.get('image_uris', {}).get('normal')
            card_text = data.get('oracle_text', 'No text available for this card.')
            if price is not None and image_url is not None:
                add_price_to_db(card_name, price, ctx.author.id)  # Add price to database with user ID
                embed = discord.Embed(title=f'Price of "{card_name}"', description=f'The price is {price}',
                                      color=0x00ff00)
                embed.set_image(url=image_url)
                embed.add_field(name="Card Text", value=card_text, inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send(f'Information not found for card #{card_number} in set {set_code}')
        else:
            await ctx.send(f'Error fetching data for card #{card_number} in set {set_code}')
    except Exception as e:
        print(f'Error in card command: {e}')
        await ctx.send('An error occurred while processing your request.')



# Run the bot
bot.run(BOT_TOKEN)

