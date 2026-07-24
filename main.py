import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn

TOKEN = "8991264173:AAEbWh11uqOx4ZgAidy-JFPseO217kk_NaI"
WEB_APP_URL = "https://solopop04.github.io/edilbingo/"


logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

user_db = {}


class DepositState(StatesGroup):
  choosing_method = State()
  waiting_for_sms = State()


class WithdrawState(StatesGroup):
  choosing_method = State()
  waiting_for_account = State()
  waiting_for_amount = State()


# --- 1. /start (እንኳን ደህና መጡ መልእክት) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  user_id = message.from_user.id
  if user_id not in user_db:
    user_db[user_id] = {
        "deposit": 0.0,
        "winnings": 0.0,
        "name": message.from_user.first_name,
    }

  await message.answer(
      f"ሰላም <b>{message.from_user.first_name}</b>! እንኳን ወደ <b>እድል ቢንጎ"
      " (EdilBingo)</b> በደህና መጡ! 🎉\n\nከታች ካለው ሜኑ ውስጥ የሚፈልጉትን መምረጥ"
      " ይችላሉ።",
      parse_mode="HTML",
  )


# --- 2. /play (PLAY (10 ብር) እና BigWin) ---
@dp.message(Command("play"))
async def cmd_play(message: types.Message):
  user_id = message.from_user.id
  if user_id not in user_db:
    user_db[user_id] = {
        "deposit": 0.0,
        "winnings": 0.0,
        "name": message.from_user.first_name,
    }

  deposit_bal = user_db[user_id]["deposit"]
  winnings_bal = user_db[user_id]["winnings"]
  total_balance = deposit_bal + winnings_bal

  daily_mode = "active" if total_balance >= 10 else "spectator"
  bigwin_mode = "active" if total_balance >= 50 else "spectator"

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🎮 PLAY (10 ብር)",
                  web_app=WebAppInfo(
                      url=f"{WEB_APP_URL}/game?type=daily&mode={daily_mode}"
                  ),
              )
          ],
          [
              InlineKeyboardButton(
                  text="🏆 BigWin ጨዋታ",
                  web_app=WebAppInfo(
                      url=f"{WEB_APP_URL}/game?type=bigwin&mode={bigwin_mode}"
                  ),
              )
          ],
      ]
  )

  await message.answer(
      "🎮 <b>የጨዋታ ምርጫዎች</b>\n\nከታች ካሉት አማራጮች አንዱን በመምረጥ መጫወት ይችላሉ፦",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# --- 3. /balance (የባላንስ እና መረጃ) ---
@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
  user_id = message.from_user.id
  if user_id not in user_db:
    user_db[user_id] = {"deposit": 0.0, "winnings": 0.0}

  user_data = user_db[user_id]
  deposit_bal = user_data["deposit"]
  winnings_bal = user_data["winnings"]
  total_balance = deposit_bal + winnings_bal

  await message.answer(
      f"👤 <b>የመገለጫ እና የባላንስ መረጃዎ</b>\n\nስም:"
      f" {message.from_user.full_name}\n💳 ያስገቡት: {deposit_bal}"
      f" ETB\n🏆 ያሸነፉት: {winnings_bal} ETB\n💰 አጠቃላይ ባላንስ: {total_balance}"
      " ETB",
      parse_mode="HTML",
  )


# --- 4. /deposit (ገንዘብ ማስገባት) ---
@dp.message(Command("deposit"))
async def cmd_deposit(message: types.Message, state: FSMContext):
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏦 CBE Birr (በንግድ ባንክ)", callback_data="dep_cbe"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📱 Telebirr (በቴሌብር)", callback_data="dep_tele"
              )
          ],
      ]
  )
  await message.answer(
      "💳 <b>ገንዘብ ማስገባት (Deposit)</b>\n\nየክፍያ አማራጭ ይምረጡ:",
      parse_mode="HTML",
      reply_markup=keyboard,
  )
  await state.set_state(DepositState.choosing_method)


# --- 5. /withdraw (ገንዘብ ማውጣት) ---
@dp.message(Command("withdraw"))
async def cmd_withdraw(message: types.Message, state: FSMContext):
  user_id = message.from_user.id
  winnings_bal = user_db.get(user_id, {}).get("winnings", 0.0)

  if winnings_bal <= 0:
    await message.answer(
        "❌ ማውጣት የሚችሉት ያሸነፉት ገንዘብ (Winnings) የለዎትም!"
    )
    return

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="🏦 CBE Birr", callback_data="wd_cbe")],
          [InlineKeyboardButton(text="📱 Telebirr", callback_data="wd_tele")],
      ]
  )
  await message.answer(
      f"🏦 <b>ገንዘብ ማውጣት</b>\nያሸነፉት: {winnings_bal} ETB",
      parse_mode="HTML",
      reply_markup=keyboard,
  )
  await state.set_state(WithdrawState.choosing_method)


# --- 6. /history (የግብይት ታሪክ) ---
@dp.message(Command("history"))
async def cmd_history(message: types.Message):
  await message.answer(
      "📜 <b>የግብይት ታሪክ</b>\nለጊዜው ምንም የተመዘገበ ግብይት የለም።",
      parse_mode="HTML",
  )


# --- 7. /instructions (የጨዋታ መመሪያ) ---
@dp.message(Command("instructions"))
async def cmd_instructions(message: types.Message):
  await message.answer(
      "❓ <b>የጨዋታ መመሪያ (Instructions):</b>\n\n1. PLAY (10 ብር) ጨዋታ 450"
      " ካርዶች አሉት።\n2. BigWin ጨዋታ 900 ካርዶች አሉት።\n3. ለእያንዳንዱ ጨዋታ"
      " እስከ 2 ካርዶች ብቻ መምረጥ ይቻላል።",
      parse_mode="HTML",
  )


# --- 8. /register (ምዝገባ) ---
@dp.message(Command("register"))
async def cmd_register(message: types.Message):
  user_id = message.from_user.id
  if user_id not in user_db:
    user_db[user_id] = {
        "deposit": 0.0,
        "winnings": 0.0,
        "name": message.from_user.first_name,
    }
  await message.answer(
      "✅ በአድል ቢንጎ (EdilBingo) በተሳካ ሁኔታ ተመዝግበዋል!", parse_mode="HTML"
  )


# --- Callback Handlers (Deposit & Withdraw logic) ---
@dp.callback_query(F.data.in_(["dep_cbe", "dep_tele"]))
async def ask_for_deposit_sms(callback: types.CallbackQuery, state: FSMContext):
  method = "CBE Birr" if callback.data == "dep_cbe" else "Telebirr"
  await state.update_data(method=method)

  prompt_text = (
      "📱 <b>የዲፖዚት መመሪያ፡</b>\n\nገንዘቡን ወደ 0913582694 (ሰለሞን ሰማው) ካስተላለፉ በኋላ"
      " የደረሰዎትን የኤስኤምኤስ (SMS) መልእክት እዚህ ላይ ፔስት (Paste) ያድርጉ።"
  )
  await callback.message.edit_text(prompt_text, parse_mode="HTML")
  await state.set_state(DepositState.waiting_for_sms)
  await callback.answer()


@dp.message(DepositState.waiting_for_sms)
async def process_deposit_sms(message: types.Message, state: FSMContext):
  sms_text = message.text
  user_id = message.from_user.id
  amount_match = re.search(
      r'(?:ETB|ብር|ETB\s*|BYR)\s*([0-9,]+\.?[0-9]*)', sms_text, re.IGNORECASE
  )
  if not amount_match:
    await message.answer("❌ ትክክለኛ የክፍያ ኤስኤምኤስ ሆኖ አልተገኘም! እንደገና ይሞክሩ።")
    return

  try:
    amount = float(amount_match.group(1).replace(",", ""))
    if user_id not in user_db:
      user_db[user_id] = {"deposit": 0.0, "winnings": 0.0}
    user_db[user_id]["deposit"] += amount
    await state.clear()
    await message.answer(
        f"✅ <b>ክፍያው ተረጋግጧል!</b> 💰 <b>{amount} ETB</b> አካውንትዎ ላይ ገብቷል።",
        parse_mode="HTML",
    )
  except Exception:
    await message.answer("❌ የገንዘብ መጠኑን ማንበብ አልተቻለም።")


@dp.callback_query(F.data.in_(["wd_cbe", "wd_tele"]))
async def ask_for_withdraw_account(callback: types.CallbackQuery, state: FSMContext):
  method = "CBE Birr" if callback.data == "wd_cbe" else "Telebirr"
  await state.update_data(method=method)
  await callback.message.edit_text(
      "🏦 አካውንት ቁጥር ወይም ስልክ ቁጥር ያስገቡ:", parse_mode="HTML"
  )
  await state.set_state(WithdrawState.waiting_for_account)
  await callback.answer()


@dp.message(WithdrawState.waiting_for_account)
async def process_withdraw_account(message: types.Message, state: FSMContext):
  await state.update_data(account_info=message.text.strip())
  user_id = message.from_user.id
  winnings_bal = user_db[user_id]["winnings"]
  await message.answer(
      f"💰 ማውጣት የሚፈልጉትን መጠን ያስገቡ (ከፍተኛው: {winnings_bal} ETB):"
  )
  await state.set_state(WithdrawState.waiting_for_amount)


@dp.message(WithdrawState.waiting_for_amount)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
  try:
    amount = float(message.text)
    user_id = message.from_user.id
    if amount <= 0 or amount > user_db[user_id]["winnings"]:
      await message.answer("❌ ያስገቡት መጠን የተሳሳተ ነው።")
      return
    user_db[user_id]["winnings"] -= amount
    await state.clear()
    await message.answer(
        f"✅ <b>የማውጣት ጥያቄዎ ተቀባይነት አግኝቷል!</b>\nድምር: {amount} ETB",
        parse_mode="HTML",
    )
  except ValueError:
    await message.answer("❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።")


# --- FastAPI Routes ---
@app.get("/game", response_class=HTMLResponse)
async def bingo_game_page(type: str = "daily", mode: str = "active"):
  try:
    with open("bingoapp/game.html", "r", encoding="utf-8") as f:
      html_content = f.read()

    is_spectator = "true" if mode == "spectator" else "false"
    min_req = "50 ብር" if type == "bigwin" else "10 ብር"
    game_title = "BigWin (900 ካርዶች)" if type == "bigwin" else "PLAY (450 ካርዶች)"
    time_val = "60" if type == "bigwin" else "5"
    card_pool_limit = 900 if type == "bigwin" else 450

    html_content = (
        html_content.replace("{{IS_SPECTATOR}}", is_spectator)
        .replace("{{MIN_REQ}}", min_req)
        .replace("{{GAME_TITLE}}", game_title)
        .replace("{{TIMER_VAL}}", time_val)
        .replace("{{CARD_POOL_LIMIT}}", str(card_pool_limit))
    )
    return HTMLResponse(content=html_content)
  except FileNotFoundError:
    return HTMLResponse(
        content=(
            "<h3>خطأ: bingoapp/game.html ፋይል አልተገኘም! እባክዎ ፋይሉን"
            " ያረጋግጡ።</h3>"
        ),
        status_code=404,
    )


async def run_bot():
  await bot.delete_webhook(drop_pending_updates=True)
  await dp.start_polling(bot)


if __name__ == "__main__":
  import threading

  server_thread = threading.Thread(
      target=lambda: uvicorn.run(app, host="127.0.0.1", port=8000), daemon=True
  )
  server_thread.start()

  asyncio.run(run_bot())
