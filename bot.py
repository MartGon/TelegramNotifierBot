import logging
import json
import datetime
import argparse
import pytz
import html

import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes

from TelegramNotifierBot.scanner import Scanner

# Pre-assign button text
YES_BUTTON = "Yes"
NO_BUTTON = "No"

async def config_command(update: Update, context: CallbackContext) -> None:

    scan_params = context.application.scanner.scan_params

    # With no args, it prints current config
    if len(context.args) == 0:
        scan_params_str = json.dumps(scan_params, indent=4)
        await send_message(update, context, "Current config:\n {}".format(scan_params_str))

    # With two args, it sets a value by key
    elif len(context.args) >= 2 and len(context.args) < 4:
        key = context.args[0]
        old_value = scan_params[key]
        
        # Check it's not a list
        if not isinstance(old_value, list):
            new_value = context.args[1]
            scan_params[key] = int(new_value) if isinstance(old_value, int) else new_value

            await send_message(update, context, "Argument {} has been updated to {} from {}".format(key, new_value, old_value))
        elif len(context.args) == 3:
            # If a list, we need more args
            operation = context.args[1]
            new_value = context.args[2]

            OP_ADD = 'add'
            OP_DEL = 'del'

            if operation == OP_ADD:
                scan_params[key].append(new_value)
                await send_message(update, context, "List has been correctly updated {}".format(scan_params[key]))
            elif operation == OP_DEL:
                scan_params[key].remove(new_value)
                await send_message(update, context, "List has been correctly updated {}".format(scan_params[key]))
            else:
                await send_message(update, context, "Unknown operation: {}. Available operations: add/del".format(operation))

        else:
            await send_message(update, context, "Argument {} is a list! Need operation add/del before value".format(key))

        # Save changes
        scan_params_str = json.dumps(scan_params, indent=4)
        with open(scan_params, "w") as text_file:
            text_file.write(scan_params_str)
    else:
        await send_message(update, context, "Incorrect number of arguments for this command")

async def restart(update: Update, context: CallbackContext) -> None:
    """
    Shuts down the bot. Should be restarted by Systemd
    """
    await context.bot.send_message(
        update.message.chat.id,
        "Bot is restarting",
        entities=update.message.entities
    )
    context.application.stop_running()

async def help(update: Update, context: CallbackContext) -> None:
    """
    Returns a list of available commands
    """
    commands = [next(iter(f.commands)) for f in context.application.handlers[0] if isinstance(f, CommandHandler)]
    message = "Avaliable commands:\n" + '\n'.join(commands)

    await context.bot.send_message(
        update.message.chat.id,
        message,
        entities=update.message.entities
    )

async def sub(update: Update, context: CallbackContext) -> None:
    """
    Registers a user to the sub list
    """
    subs = context.application.subs
    subs[update.message.chat_id] = True

    config = context.application.bot.config
    with open(config["subs_file"], "w") as f:
        json.dump(subs, f)

    await context.bot.send_message(
            update.message.chat_id,
            "You're now subscribed!",
            entities=update.message.entities
        )
    
async def unsub(update: Update, context: CallbackContext) -> None:
    """
    Unregisters a user to the sub list
    """
    subs = context.application.subs
    user = update.message.chat_id
    if user in subs:
        subs.pop(user)
    
    await context.bot.send_message(
            user,
            "You're no longer subscribed! :(",
            entities=update.message.entities
        )

async def list_subs(update: Update, context: CallbackContext) -> None:
    """
    Lists subscribed users
    """
    subs = context.application.subs
    for sub, _ in subs.items():
        await context.bot.send_message(
            update.message.chat_id,
            str(sub),
        )

async def resend(update: Update, context: CallbackContext) -> None:

    if len(context.args) == 1 and context.args[0].isdigit():
        date_str = get_date_str(int(context.args[0]))
        await context.bot.send_message(
            update.message.chat_id,
            "Sending notifications of unmarked posts since {}".format(date_str),
        )
        
        scanner = context.application.scanner
        headers = ["id", "title", "selftext", "over_18", "location", "age", "flair", "author", "online", "permalink", "created_utc", "notified", "interested"]
        posts = scanner.get_unmarked_posts(headers, date_str)
        logging.debug("Unmarked posts {}".format(len(posts)))
        for p in posts:
            msg = scanner.get_post_message(p)
            await send_prompt_post_msg(context.bot, update.message.chat_id, msg, p)
            scanner.mark_post_as_notified(p['id'])
    else:
        await context.bot.send_message(
            update.message.chat_id,
            "Incorrect use of command. Needs one digit argument: days",
        )

async def interested(update: Update, context: CallbackContext) -> None:

    if len(context.args) == 1 and context.args[0].isdigit():
        date_str = get_date_str(int(context.args[0]))
        print(date_str)
        await context.bot.send_message(
            update.message.chat_id,
            "Sending notifications of interested posts since {}".format(date_str),
        )
        
        scanner = context.application.scanner
        headers = ["id", "title", "selftext", "over_18", "location", "age", "flair", "author", "online", "permalink", "created_utc", "notified", "interested"]
        posts = scanner.get_interested_posts(headers, date_str)
        logging.debug("Interested posts {}".format(len(posts)))
        for p in posts:
            msg = scanner.get_post_message(p)
            await send_post_msg(context.bot, update.message.chat_id, msg, p)
    else:
        await context.bot.send_message(
            update.message.chat_id,
            "Incorrect use of command. Needs one digit argument: days",
        )

async def send_message(update: Update, context: CallbackContext, message: str) -> None:

    await context.bot.send_message(
        update.message.chat_id,
        message,
    )

def get_date_str(days_before: int) -> str:
    now = datetime.datetime.now()
    past_day = now - datetime.timedelta(days=days_before)
    date_str = past_day.strftime("%Y-%m-%d %H:%M:%S")

    return date_str

async def send_post_msg(bot: telegram.Bot, sub: str, message: str, p: dict, buttons=None) -> None:
    await bot.send_message(sub, message, parse_mode=ParseMode.HTML, reply_markup=buttons)

async def send_prompt_post_msg(bot: telegram.Bot, sub: str, message: str, p: dict) -> None:
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(YES_BUTTON, callback_data=YES_BUTTON + '-' + p['id']),
        InlineKeyboardButton(NO_BUTTON, callback_data=NO_BUTTON + '-' + p['id']),
    ]])
    await send_post_msg(bot, sub, message, p, buttons)
    logging.debug("Notification sent to sub {} about: {}".format(sub, p['title']))

async def button_tap(update: Update, context: CallbackContext) -> None:
    """
    This handler processes the inline buttons on the menu
    """

    data = update.callback_query.data.split('-')

    if data[0] == YES_BUTTON:
        interested = True        
    elif data[0] == NO_BUTTON:
        interested = False    

    # Mark post as interested
    post_id = data[1]
    scanner = context.application.scanner
    scanner.mark_post_as_interested(post_id, interested)

    # Close the query to end the client-side loading animation
    await update.callback_query.answer()

    # Update message content with corresponding menu section
    await update.callback_query.edit_message_reply_markup(
        None
    )

    await context.bot.send_message(
        update.callback_query.message.chat_id,
        "Interested status of post has been succesfully updated to: {}".format(interested),
    )

async def send_updates(context: ContextTypes.DEFAULT_TYPE) -> None:

    bot = context.application.bot
    subs = context.application.subs
    scanner = context.application.scanner

    # Scan for valid posts
    posts_to_notify = await scanner.scan()
    logging.debug("Seding update to the following subs {}".format(subs))

    # Send notifications
    for s, _ in subs.items():
        for p in posts_to_notify:
            msg = scanner.get_post_message(p)
            await send_prompt_post_msg(bot, s, msg, p)
            logging.debug("Notification sent to sub {} about: {}".format(s, p['title']))
        
            # Mark as notified
            scanner.mark_post_as_notified(p['id'])

# NOTES - TODO
# Send a notification right away, config
# Create a rate system. request the top of the week

class TelegramBot:

    def __init__(self, config : dict, scanner : Scanner, verbosity : int):
        self.config = config
        self.scanner = scanner
        self.verbosity = verbosity

    def start(self):
        logging.basicConfig(format='%(levelname)s: %(message)s', level=self.verbosity)

        subs = json.loads(open(self.config["subs_file"]).read())

        self.application = ApplicationBuilder().token(self.config['bot_token']).build()
        application = self.application
        application.scanner = self.scanner
        application.subs = subs

        # Register commands
        application.add_handler(CommandHandler("sub", sub))
        application.add_handler(CommandHandler("unsub", unsub))
        application.add_handler(CommandHandler("resend", resend))
        application.add_handler(CommandHandler("interested", interested))
        application.add_handler(CommandHandler("list", list_subs))
        application.add_handler(CommandHandler("help", help))
        application.add_handler(CommandHandler("restart", restart))
        application.add_handler(CommandHandler("config", config_command))

        # Register handler for inline buttons
        application.add_handler(CallbackQueryHandler(button_tap))

        # Echo any message that is not a command
        # dispatcher.add_handler(MessageHandler(~Filters.command, echo))

        # Start the Bot
        logging.info("Bot initatied. Waiting {} seconds until start".format(self.config['startup_secs']))
        application.job_queue.run_once(send_updates, self.config['startup_secs'])
        application.job_queue.run_daily(send_updates, datetime.time(hour=int(self.config['update_hour']), minute=00, tzinfo=pytz.timezone('Europe/Madrid')))

    def run(self):
        self.application.run_polling()