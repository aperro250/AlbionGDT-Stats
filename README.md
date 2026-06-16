# 🎮 AlbionGDT-Stats

As the project name suggests, this project generates daily guild member statistics for Albion Online and sends them to a selected Discord chat.

<table>
  <tr>
    <td valign="top">
      <img src="ReadmeAssets/Images/Discord_Message1.png" width="300" alt="Title, kill, Death and PVE Fame">
    </td>
    <td valign="bottom">
      <img src="ReadmeAssets/Images/Discord_Message2.png" width="300" alt="Gathering and Crafting Fame">
    </td>
  </tr>
</table>

# 👁️‍🗨️ The project usage

There used to be a Discord bot, Albion Tools, that sent daily information about members, but at the moment it has some server issues and does not work.

As a solution, I did my own investigation about ***where it obtained the data?***, and wrote this project to create a fully automatic and **FREE** Discord bot that sends daily statistics to a selected Discord channel. I will explain below in the installation guide how it works and where the data comes from if you want to investigate or are just interested in the code functionality.

# ❗ IMPORTANT

***This project manages current information, and the data in the database is from yesterday, so the daily statistics are not for today, they are for yesterday!***

# 1.🛠️ Installation guide

## 1.1 ⏬ Download

**Clone this repository** from github

```bash
git clone https://github.com/aperro250/AlbionGDT-Stats.git
cd AlbionGDT-Stats
```

Now, download the required Python packages *(discord.py and requests)*. They are listed in **requirements.txt**

```bash
pip install -r requirements.txt
```

### 🔴 error: externally-managed-environment

If you get the error **error: externally-managed-environment**, you must create a virtual Python environment and from then on run the commands inside it. To create it, run the following command:

```bash
python -m venv venv
```

And enter the environment. Also, **VERY IMPORTANT**, if you restart the console, you need to run this command again to use the installed Python packages.

**WINDOWS**

```bash
source venv/Scripts/activate
```

**LINUX**

```bash
source venv/bin/activate
```

Now run the Python requirements command from before.

# 2 ⚙️ Configuration

Now, when everything is installed, let's make the code work.

Locate the file **config.json**, which contains the configuration.

Here is the file syntax:

```json
{
    "discord_token": "DISCORD_TOKEN",
    "guild_id": "ALBION_GUILD_ID",
    "channels": {
        "rating":[
            FIRST_DISCORD_CHANNEL_ID,
            SECOND_DISCORD_CHANNEL_ID,
            ...
        ]
    }
}
```

Yes, it supports multiple Discord channels, but it also works with only one, so the others are optional.

### 2.1 🤖 Obtain discord bot token

Go to the [Discord Devoloper Portal](https://discord.com/developers/home) and create your Discord bot.

After it is created, go to your bot **"Application"** and access the **Bot** settings section. Look for the **Token** section and press the regeneration button. It will give you the bot token, which you can then paste into the config.

![](ReadmeAssets/Images/Discord_Bot.png)

### 2.2 📋 Obtain the Albion Online Guild ID

To obtain your guild ID, I recommend using external sources. I used [Albion Online Tools](https://albiononlinetools.com/), you can [search the guild](https://albiononlinetools.com/player/guildfinder.php) and in the information section you will see the guild id.

![](ReadmeAssets/Images/Guild_ID.png)

### 2.3 🗨️ Obtain Discord Chat ID

***It's optional, the bot can automatically configure that section in the future.***

You can obtain the Discord chat ID by right-clicking the chat and selecting the last option, **"Copy chat ID"**

# 3 🐍 Running the code

When all requirements and the configuration file are ready, you can run the code. The project has 2 runtime entry points and 1 that runs everything at once.

### 3.1 ▶️ The main run file (Run_daily.py)

This will be the most run file. It first runs **Take_Snapshoot.py** and retrieves the current information, then runs the command */send-daily-stats* from **discord_bot.py** and sends the statistics to all channels written in config.json.

To run this file, use:

```bash
python run_daily.py
```

### 3.2 1️⃣ Update the database or make a *Snapshoot* (Take_Snapshoot.py)

This script updates the database (albion_guild_stats.db) and calculates daily information, doing *today_information - yesterday_information =* and obtaining the daily statistics, or as I call it, the **delta** variable.

To run this file, use:

```bash
python Take_Snapshoot.py
```

Also, you can access the database to view the full history. It's an SQLite database, and you can open it using any graphical SQLite viewer. In my example, I used **DB Browser for SQLite**, but you can use any tool you prefer.

### 3.3 ️️2️⃣ Launch the Discord Bot (discord_bot.py)

This script launches the Discord bot, and if you run it directly, it will keep running. However, if it is started from run_daily, it will only run long enough to send the statistics. In general, if you want to use the commands below, you need to run this script manually.

To run this file, use:

```bash
python discord_bot.py
```

When the bot is activated, you can type "/" in the chat and select the bot to view its commands. I will list them below and explain each one.

***/send-daily-stats***

☝️ Sends the daily statistics to the channel where the command was executed. It does not update the guild member database, so if you have not updated the database, the statistics will not be accurate.

***/set-channel report_type:rating***

☝️ Adds the current channel as a destination where the daily statistics will be sent automatically. **It appends to the list instead of overwriting it.**

***/set-guild-id guild_id:YOUR_GUILD_ID***

☝️ **Sets** the provided ID as the new guild to fetch information from. **THIS WILL REPLACE THE PREVIOUS GUILD ID.**
