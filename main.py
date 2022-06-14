import discord
import sqlite3
from pytz import timezone
from config import *
from datetime import datetime
from random import choices, randint
from discord.ext import tasks

# Create bot instance
intents = discord.Intents.all()
bot = discord.Bot(intents=intents)

# Set timezone
eastern = timezone('US/Eastern')

# Create sqlite connection
con = sqlite3.connect("time.db")
cursor = con.cursor()

# Create initial database
cursor.execute("CREATE TABLE if not exists data(id INTEGER PRIMARY KEY AUTOINCREMENT, user varchar(18), timeIn TEXT, timeOut TEXT NULL, totalTime TEXT NULL, checked tinyint(1) DEFAULT 0)")

# When bot is started
@bot.event
async def on_ready():
    # Print login message (useful for Pterodactyl)
    print(f"We have logged in as {bot.user}")

    # Set bot status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="time"), status='online')

    # Start clock to check time
    check_clock.start()

# Clock in command
@bot.slash_command(guild_ids=[Config.guild], description="Clock in")
async def clockin(ctx):
    # Check database for user already being logged in
    cursor.execute(f"SELECT * FROM data WHERE user = {ctx.author.id} AND timeOut IS NULL")
    user = cursor.fetchone()

    if user is None:
        # Get time started
        time = datetime.now(eastern)

        # Insert into database
        sql = "INSERT INTO data(user, timeIn) VALUES (?, ?)"
        val = (ctx.author.id, time)
        cursor.execute(sql, val)
        con.commit()

        # Create log and respond to user
        embed = await embed_builder("You've Been Clocked In", f"You've been clocked in at {time.strftime('%I:%M:%S %p')} EST")
        await create_log("User Clocked In", f"{ctx.author.mention} clocked in at {time.strftime('%I:%M:%S %p')} EST")
        await ctx.respond(embed=embed, ephemeral=True)
    else:
        # Get time user clocked in and respond to user
        time = datetime.fromisoformat(user[2])
        embed = await embed_builder("You're Already Clocked In", f"You already clocked in at {time.strftime('%I:%M:%S %p')}")
        await ctx.respond(embed=embed, ephemeral=True)

# Clock out command
@bot.slash_command(guild_ids=[Config.guild], description="Clock out")
async def clockout(ctx):
    # Check database for user already being logged in
    cursor.execute(f"SELECT * FROM data WHERE user = {ctx.author.id} AND timeOut IS NULL")
    user = cursor.fetchone()

    if user is not None:
        # Get time user started and time ended
        endTime = datetime.now(eastern)
        startTime = datetime.fromisoformat(user[2])

        # Get total time and setup standard use for future usage
        hours, minutes, seconds = await time_between(startTime, endTime)
        totalTime = str(hours) + ":" + str(minutes) + ":" + str(seconds)

        # Update row and set timeOut and totalTime
        sql = "UPDATE data SET timeOut = ?, totalTime = ? WHERE id = ?"
        val = (endTime, totalTime, user[0])
        cursor.execute(sql, val)
        con.commit()

        # Build fields for log
        fields = {"Name": ctx.author.display_name, "Start Time": startTime.strftime('%I:%M:%S %p') + " EST", "End Time": endTime.strftime('%I:%M:%S %p') + " EST"}
        totalTimeStr = ""

        # Determine if to use singular or plural verbage
        if(hours > 1 or hours == 0):
            totalTimeStr = str(hours) + " hours, "
        elif(hours == 1):
            totalTimeStr = str(hours) + " hour, "
        
        if(minutes > 1 or minutes == 0):
            totalTimeStr += str(minutes) + " minutes, "
        elif(minutes == 1):
            totalTimeStr += str(minutes) + " minute, "

        if(seconds > 1 or seconds == 0):
            totalTimeStr += str(seconds) + " seconds"
        elif(seconds == 1):
            totalTimeStr += str(seconds) + " second"

        # Set total time for both logging and user
        fields['Total Time'] = totalTimeStr
        
        # Create log
        await create_log("User Clocked Out", f"{ctx.author.mention} clocked out at {endTime.strftime('%I:%M:%S %p')} EST", fields=fields)

        # Respond to user
        embed = await embed_builder("You've been clocked out", f"You've been clocked out at {endTime.strftime('%I:%M:%S %p')} EST.")
        embed.add_field(name="Total Time", value=totalTimeStr, inline=False)
        await ctx.respond(embed=embed, ephemeral=True)
    else:
        # Respond to user
        embed = await embed_builder("You're Not Clocked In", "You're not currently clocked in")
        await ctx.respond(embed=embed, ephemeral=True)

# Check for user being clocked in for over two hours
@tasks.loop(minutes=1)
async def check_clock():
    # Get database items that haven't been checked
    cursor.execute("SELECT * FROM data WHERE checked = 0")
    users = cursor.fetchall()

    # Loop through users
    for user in users:
        # Get currentTime and startTime for comparison
        currentTime = datetime.now(eastern)
        startTime = datetime.fromisoformat(user[2])
        
        # Determine difference
        hours, minutes, seconds = await time_between(startTime, currentTime)

        # If it's been two hours
        if(hours == 2):
            # Get user and set fields for log
            userObj = bot.get_user(int(user[1]))
            fields = {"Start Time": startTime.strftime('%I:%M:%S %p'), "Current Time": currentTime.strftime('%I:%M:%S %p')}

            # Send log
            await create_log("User Clocked In For Two Hours", f"{userObj.mention} has been clocked in for two hours", fields=fields)

            # Send DM to user with information
            embed = await embed_builder("Clocked In For Two Hours", "You've been clocked in for over two hours")
            for k, v in fields.items():
                embed.add_field(name=k, value=v, inline=False)
            await userObj.send(embed=embed)

            # Update database to mark as checked
            sql = "UPDATE data SET checked = ? WHERE id = ?"
            val = (1, user[0])
            cursor.execute(sql, val)
            con.commit()

# Function for building embeds
async def embed_builder(title, description):
    # Create embed
    embed = discord.Embed(title=title, description=description, color=discord.Color.from_rgb(255, 0, 0))

    return embed

# Given hour, minute, second difference between two times
async def time_between(earlier, later):
    difference = later - earlier
    minutes, seconds = divmod(difference.seconds, 60)
    hours, minutes = divmod(minutes,60)

    return hours, minutes, seconds

# Create a log
async def create_log(title, message, fields = None):
    embed = await embed_builder(title, message)

    if fields is not None:
        for k, v in fields.items():
            embed.add_field(name=k, value=v, inline=False)
        
    channel = bot.get_channel(Config.log_channel)
    await channel.send(embed=embed)


bot.run(Config.token)