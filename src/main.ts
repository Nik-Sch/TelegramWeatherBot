import { Telegraf } from "telegraf";

const bot = new Telegraf(process.env.BOT_TOKEN || '');

bot.start((ctx) => ctx.reply(`Send me locations and I will answer with the weather.`));

bot.on('location', ctx => {
  ctx.reply(JSON.stringify(ctx.message.location));
});

bot.launch();
