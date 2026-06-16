
# 🎮 AlbionGDT-Stats

As the project name suggests, this project generates daily guild member statistics for Albion Online, and sends it to selected Discord chat.

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
There was a Discord bot, Albion Tools, that has sended daily information about members, but at the actual time it haves some servers troubles and didn't work.

As the solusion, i had my own investigation about ***where did it obtain the data?***, and writed this project to make a totally automatic and **FREE** discord bot that sends daily statistic to selected discord channel. I will explaine downside the installation guide about how it works and where the data comes if you wanna investigate or just are interted about code funcionality.

# ❗ IMPORTANT

***This proyects manages the actual information, and the actual information in the databases its from yesterday, so the daily statistic it's not for today, it's for yesterday!***
# 1.🛠️ Installation guide

## 1.1 ⏬ Download 

**Clone this repository** from github

```bash
git clone https://github.com/aperro250/AlbionGDT-Stats.git
cd AlbionGDT-Stats
```
Now, download the needed python packages *(discord.py and requests)*. There stored in **requirements.txt**
```bash
pip install -r requirements.txt
```
### 🔴 error: externally-managed-environment
 If youre had an error **error: externally-managed-environment** , you must create a virtual python environment and from now run the commands from it. To create in, run the next command:
```bash
python -m venv venv
```
And enter the environment. Also, **VERY INMPORTANT**, if you restart the console, you need to run this command again to use the installed python packages.

**WINDOWS**
```bash
source venv/Scripts/activate
```
**LINUX**
```bash
source venv/bin/activate
```

Now run the python requirements command from before.

# 2 ⚙️ Configuration

Now, when all is installed, lets make the code work.

Locate the file **config.json**, that the file with the configuration.

Here is the file syntaxis:

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
Yes, its working with multiple discord channel, but it also work with only one, so the others are optional.

### 2.1 🤖 Obtain discord bot token

Go to the [Discord Devoloper Portal](https://discord.com/developers/home) and create your Discord bot.
When it created, go to your bot **"Aplication"** and acces the **Bot** settings section. Look for the **Token** section and press the regeneration button. It will give you the bot token, and you can now paste it to config.

![](ReadmeAssets/Images/Discord_Bot.png)

### 2.2 📋 Obtain the Albion Online Guild ID

To obtain your guild ID, i recomend you to use external sourses. I had used [Albion Online Tools](https://albiononlinetools.com/), you can [search the guild](https://albiononlinetools.com/player/guildfinder.php) and in the information section you will see the guild id.
![](ReadmeAssets/Images/Guild_ID.png)

### 2.3 🗨️ Obtain Discord Chat ID

***Its optional, the bot can automaticlly configure that section in future.***

You can obtain the discord chat id by right-clicking to the chat and selecting the last option, **"Copy chat ID"**

# 3 🐍 Runing the code

When all requirements and the configuration file are done, you can run the code. The proyect has 2 runtime points and 1 that run all for one time.

### 3.1 ▶️ The main run file (Run_daily.py)

This will be the most runed file. He first run **Take_Snapshoot.py** and takes the actual information, then run the command */send-daily-stats* from **discord_bot.py** and sends the statistic to all the channels written in config.json

To run this file, run this command:

```bash
python run_daily.py
```

### 3.2 1️⃣ Update the database or make a *Snapshoot* (Take_Snapshoot.py)

This script updates the database (albion_guild_stats.db) and calculates a daily information, making *today_information - yesterday_information =* and obtaining the daily statistic, or as I name it, the **delta** variable.

To run this file, run this command:

```bash
python Take_Snapshoot.py
```
Also you can access to the database to view all the history. Its a SQL Database, and you can open it graphically with external program. In my example, I used **DB Browser for SQLite**, but you can use anyone that you prefer.

###  3.3 ️️2️⃣ Launch the Discord Bot (discord_bot.py)

This script launches the Discord bot and if you run it from here, it will stay, but if from run_daily it will only activates to send the statistic. In general, if you wanna use the comand from below, you need to run manually this script.

To run this file, run this command:

```bash
python discord_bot.py
```

When the bot will be activated, you can write a "/" in the chat and select the bot to view his commands. Also, I will write them down here and explain everyone.

***/send-daily-stats***

☝️Sends to the channel where you sended the command a daily statistic. It doesn't update the guild member database, so if you didn't updates the dabase, the statistic will not be true.

***/set-channel report_type:rating***

☝️Add the channel where the command was sended as the point where will be sended automaticlly the daily statistic. **It adds to the list and no rewrites it.**

***/set-guild-id guild_id:YOUR_GUILD_ID***

☝️**Sets** the given id as the new guild to take information about it. **IT WILL REWRITE THE PAST ID.**


