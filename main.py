import asyncio
import logging
import random
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn

TOKEN = "8991264173:AAEbWh11uqOx4ZgAidy-JFPseO217kk_NaI"
# ቦቱ እና ሰርቨሩ በአንድ ላይ በአካባቢያዊ ኔትወርክ ወይም በሰርቨር ሲሰራ
WEB_APP_URL = "http://127.0.0.1:8000"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

# ዳታቤዝ፡ deposit (ያስገቡት - ማውጣት አይቻልም) እና winnings (ያሸነፉት - ማውጣት የሚቻለው)
user_db = {}


class DepositState(StatesGroup):
  choosing_method = State()
  waiting_for_sms = State()


class WithdrawState(StatesGroup):
  choosing_method = State()
  waiting_for_account = State()
  waiting_for_amount = State()


# ==========================================
# የቢንጎ የቀለም አከፋፈል እና የጥሪ ዕድል ሎጂክ (Python Backend)
# ==========================================
def get_bingo_cell_style(number):
  """
  ቁጥሩን መሰረት በማድረግ ተገቢውን የ BINGO ፊደል፣ ከለር እና የ CSS ክላስ ያዘጋጃል።
  - B (1-15): አረንጓዴ (#27ae60)
  - I (16-30): ቀይ (#c0392b)
  - N (31-45): ወሃ ሰማያዊ (#5dade2)
  - G (46-60): ሰማያዊ (#2980b9)
  - O (61-75): ብርቱካናማ (#d35400)
  """
  if 1 <= number <= 15:
    return {'letter': 'B', 'color': '#27ae60', 'class': 'bingo-cell-b'}
  elif 16 <= number <= 30:
    return {'letter': 'I', 'color': '#c0392b', 'class': 'bingo-cell-i'}
  elif 31 <= number <= 45:
    return {'letter': 'N', 'color': '#5dade2', 'class': 'bingo-cell-n'}
  elif 46 <= number <= 60:
    return {'letter': 'G', 'color': '#2980b9', 'class': 'bingo-cell-g'}
  elif 61 <= number <= 75:
    return {'letter': 'O', 'color': '#d35400', 'class': 'bingo-cell-o'}
  else:
    return {'letter': '', 'color': '#000000', 'class': ''}


def get_one_line_winning_calls():
  """
  የአንድ መስመር (የዘውትር ጨዋታ) አሸናፊ የሚወጣበትን የጥሪ ብዛት 
  በተጠየቀው መቶኛ ስርጭት መሰረት በዘፈቀደ ይመርጣል፡
  - ከ13 እስከ 15 ጥሪ: 80%
  - ከ15 እስከ 18 ጥሪ: 15%
  - ከ18 እስከ 20 ጥሪ: 3%
  - ከ10 እስከ 13 ጥሪ: 2%
  """
  ranges = [
      (list(range(13, 16)), 80),  # 13 - 15 ጥሪ (80%)
      (list(range(15, 19)), 15),  # 15 - 18 ጥሪ (15%)
      (list(range(18, 21)), 3),   # 18 - 20 ጥሪ (3%)
      (list(range(10, 13)), 2)    # 10 - 13 ጥሪ (2%)
  ]
  
  weights = [weight for _, weight in ranges]
  chosen_range = random.choices([r for r, _ in ranges], weights=weights, k=1)[0]
  winning_turn = random.choice(chosen_range)
  return winning_turn


# 1. /start ትዕዛዝ እና ዋናው ሜኑ (ከ 10 እና 50 ብር ገደብ ማረጋገጫ ጋር)
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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

  # የጨዋታ ሁነታዎችን በባላንስ ገደብ መወሰን (የዘውትር: 10 ብር, BigWin: 50 ብር)
  daily_mode = "active" if total_balance >= 10 else "spectator"
  bigwin_mode = "active" if total_balance >= 50 else "spectator"

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🎮 የዘውትር ጨዋታ (ባለ 10 ብር)",
                  web_app=WebAppInfo(url=f"{WEB_APP_URL}/game?type=daily&mode={daily_mode}"),
              )
          ],
          [
              InlineKeyboardButton(
                  text="🏆 BigWin ጨዋታ (ባለ 50 ብር - በሳምንት 2 ቀን)",
                  web_app=WebAppInfo(url=f"{WEB_APP_URL}/game?type=bigwin&mode={bigwin_mode}"),
              )
          ],
          [
              InlineKeyboardButton(
                  text="💳 ገንዘብ አስገባ (Deposit)", callback_data="deposit_menu"
              ),
              InlineKeyboardButton(
                  text="🏦 ገንዘብ አውጣ (Withdraw)", callback_data="withdraw_menu"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📊 አካውንት ፕሬፋይል/ባላንስ", callback_data="profile"
              )
          ],
      ]
  )

  welcome_text = (
      f"ሰላም <b>{message.from_user.first_name}</b> ወደ <b>EdilBingo</b> እንኳን ደህና"
      f" መጡ!\n\n💰 አጠቃላይ ባላንስ: <b>{total_balance} ETB</b>\n(💳 ያስገቡት:"
      f" {deposit_bal} ETB | 🏆 ያሸነፉት: {winnings_bal} ETB)\n\n"
  )

  if total_balance < 10:
    welcome_text += (
        "⚠️ <i>ማስታወሻ:</i> አካውንትዎ ላይ ከ 10 ብር በታች ስለሆነ የዘውትር ጨዋታን በንቃት"
        " መጫወት አይችሉም (BigWin ደግሞ 50 ብር ይጠይቃል)፤ ነገር ግን እንደ <b>Spectator"
        " (ተመልካች)</b> ቁጥሮችን እና አሸናፊዎችን መከታተል ይችላሉ። ለመጫወት <b>Deposit</b> ያድርጉ!"
    )
  else:
    welcome_text += "✨ ከታች ካሉት የጨዋታ አይነቶች አንዱን በመምረጥ መጫወት ይችላሉ፦"

  await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


# 2. የፕሮፋይል እና ባላንስ ማሳያ
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  user_data = user_db.get(user_id, {"deposit": 0.0, "winnings": 0.0})
  deposit_bal = user_data["deposit"]
  winnings_bal = user_data["winnings"]
  total_balance = deposit_bal + winnings_bal

  status_text = (
      "ፈጣን ተጫዋች (Active Player)"
      if total_balance >= 10
      else "ተመልካች ብቻ (Spectator - ባላንስ ከ 10 ብር በታች ነው)"
  )

  keyboard = InlineKeyboardMarkup(inline_keyboard=[[
      InlineKeyboardButton(text="🔙 ወደ ዋናው ሜኑ", callback_data="main_menu")
  ]])

  await callback.message.edit_text(
      f"👤 <b>የመገለጫ መረጃዎ (Profile)</b>\n\nስም:"
      f" {callback.from_user.full_name}\n💳 ያስገቡት ገንዘብ: {deposit_bal}"
      f" ETB\n🏆 ያሸነፉት/የበሉት: {winnings_bal} ETB\n💰 አጠቃላይ ባላንስ:"
      f" {total_balance} ETB\nሁኔታ: {status_text}",
      parse_mode="HTML",
      reply_markup=keyboard,
  )


# 3. የ DEPOSIT ሎጂክ
@dp.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: types.CallbackQuery, state: FSMContext):
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
          [
              InlineKeyboardButton(text="🔙 ወደ ዋናው ሜኑ", callback_data="main_menu")
          ],
      ]
  )
  await callback.message.edit_text(
      "💳 <b>ገንዘብ ማስገባት (Deposit)</b>\n\nእባክዎ ገንዘብ ያስገቡበትን የክፍያ አማራጭ"
      " ይምረጡ:",
      parse_mode="HTML",
      reply_markup=keyboard,
  )
  await state.set_state(DepositState.choosing_method)
  await callback.answer()


@dp.callback_query(F.data.in_(["dep_cbe", "dep_tele"]))
async def ask_for_deposit_sms(callback: types.CallbackQuery, state: FSMContext):
  method = "CBE Birr" if callback.data == "dep_cbe" else "Telebirr"
  await state.update_data(method=method)

  if callback.data == "dep_tele":
    prompt_text = (
        "📱 <b>Telebirr የዲፖዚት መመሪያ፡</b>\n\nእባክዎ ገንዘቡን በሚከተለው የቴሌብር"
        " አካውንት ያስተላልፉ፡\n- ስም: <b>ሰለሞን ሰማው</b>\n- ስልክ ቁጥር: <b>0913582694</b>"
        " (913582694)\n\nገንዘቡን ከላኩ በኋላ የደረሰዎትን የክፍያ መልእክት (SMS) ኮፒ አድርገው"
        " እዚህ ላይ ይለጥፉ (Paste ያድርጉ)።"
    )
  else:
    prompt_text = (
        "🏦 <b>CBE Birr የዲፖዚት ማረጋገጫ፡</b>\n\nከ CBE Birr የደረሰዎትን የክፍያ"
        " መልእክት (SMS) ኮፒ አድርገው እዚህ ላይ ይለጥፉ (Paste ያድርጉ)። ሲስተሙ በአውቶማቲክ"
        " አረጋግጦ ባላንስዎን ያስገባል!"
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
    await message.answer(
        "❌ ያስገቡት ጽሁፍ ትክክለኛ የክፍያ መልእክት (SMS) ሆኖ አልተገኘም! እባክዎ እንደገና"
        " ይሞክሩ።"
    )
    return

  try:
    amount = float(amount_match.group(1).replace(",", ""))
    if amount <= 0:
      raise ValueError()
    if user_id not in user_db:
      user_db[user_id] = {"deposit": 0.0, "winnings": 0.0}
    user_db[user_id]["deposit"] += amount
    await state.clear()
    await message.answer(
        f"✅ <b>ክፍያው በትክክል ተረጋግጧል!</b>\n\n💰 <b>{amount} ETB</b> ወደ"
        " አካውንትዎ ገብቷል። /start በመጫን ይመለሱ።",
        parse_mode="HTML",
    )
  except Exception:
    await message.answer("❌ የገንዘብ መጠኑን ማንበብ አልተቻለም።")


# 4. የ WITHDRAW ሎጂክ
@dp.callback_query(F.data == "withdraw_menu")
async def withdraw_menu(callback: types.CallbackQuery, state: FSMContext):
  user_id = callback.from_user.id
  winnings_bal = user_db.get(user_id, {}).get("winnings", 0.0)

  if winnings_bal <= 0:
    await callback.answer(
        "❌ ማውጣት የሚችሉት ያሸነፉት ገንዘብ የለዎትም! (ያስገቡትን ማውጣት አይቻልም)",
        show_alert=True,
    )
    return

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🏦 CBE Birr (አካውንት ቁጥር)", callback_data="wd_cbe"
              )
          ],
          [
              InlineKeyboardButton(
                  text="📱 Telebirr (ስልክ ቁጥር)", callback_data="wd_tele"
              )
          ],
          [
              InlineKeyboardButton(text="🔙 ወደ ዋናው ሜኑ", callback_data="main_menu")
          ],
      ]
  )
  await callback.message.edit_text(
      f"🏦 <b>ገንዘብ ማውጣት (Withdraw)</b>\n\nያሸነፉት ባላንስ: <b>{winnings_bal}"
      f" ETB</b>\nአማራጭ ይምረጡ:",
      parse_mode="HTML",
      reply_markup=keyboard,
  )
  await state.set_state(WithdrawState.choosing_method)
  await callback.answer()


@dp.callback_query(F.data.in_(["wd_cbe", "wd_tele"]))
async def ask_for_withdraw_account(callback: types.CallbackQuery, state: FSMContext):
  method = "CBE Birr" if callback.data == "wd_cbe" else "Telebirr"
  await state.update_data(method=method)
  prompt_text = (
      "🏦 የንግድ ባንክ (CBE) <b>አካውንት ቁጥርዎን</b> ያስገቡ:"
      if method == "CBE Birr"
      else "📱 የቴሌብር <b>ስልክ ቁጥርዎን</b> (09...) ያስገቡ:"
  )
  await callback.message.edit_text(prompt_text, parse_mode="HTML")
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
    current_winnings = user_db[user_id]["winnings"]
    if amount <= 0 or amount > current_winnings:
      await message.answer("❌ ያስገቡት መጠን የተሳሳተ ነው ወይም ከያሸነፉት ይበልጣል።")
      return
    user_db[user_id]["winnings"] -= amount
    data = await state.get_data()
    await state.clear()
    await message.answer(
        f"✅ <b>የማውጣት ጥያቄዎ ተቀባይነት አግኝቷል!</b>\nድምር: {amount}"
        " ETB\nበአጭር ጊዜ ውስጥ ይላካል። /start በመጫን ይመለሱ።",
        parse_mode="HTML",
    )
  except ValueError:
    await message.answer("❌ እባክዎ ትክክለኛ ቁጥር ያስገቡ።")


@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  user_data = user_db.get(user_id, {"deposit": 0.0, "winnings": 0.0})
  total_balance = user_data["deposit"] + user_data["winnings"]

  daily_mode = "active" if total_balance >= 10 else "spectator"
  bigwin_mode = "active" if total_balance >= 50 else "spectator"

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🎮 የዘውትር ጨዋታ (ባለ 10 ብር)",
                  web_app=WebAppInfo(url=f"{WEB_APP_URL}/game?type=daily&mode={daily_mode}"),
              )
          ],
          [
              InlineKeyboardButton(
                  text="🏆 BigWin ጨዋታ (ባለ 50 ብር - በሳምንት 2 ቀን)",
                  web_app=WebAppInfo(url=f"{WEB_APP_URL}/game?type=bigwin&mode={bigwin_mode}"),
              )
          ],
          [
              InlineKeyboardButton(
                  text="💳 ገንዘብ አስገባ (Deposit)", callback_data="deposit_menu"
              ),
              InlineKeyboardButton(
                  text="🏦 ገንዘብ አውጣ (Withdraw)", callback_data="withdraw_menu"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📊 አካውንት ፕሬፋይል/ባላንስ", callback_data="profile"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      f"🏠 <b>EdilBingo ዋና ሜኑ</b>\n\n💰 አጠቃላይ ባላንስ: {total_balance} ETB",
      reply_markup=keyboard,
      parse_mode="HTML",
  )


# ==========================================
# 5. የ MINI APP WEB SERVER & FULL BINGO LOGIC (Spectator Mode Integration)
# ==========================================
@app.get("/game", response_class=HTMLResponse)
async def bingo_game_page(type: str = "daily", mode: str = "active"):
  is_spectator = (mode == "spectator")
  min_req = "50 ብር" if type == "bigwin" else "10 ብር"
  
  return f"""
    <!DOCTYPE html>
    <html lang="am">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EdilBingo - {type.upper()}</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; background: #0f172a; color: #fff; text-align: center; margin: 0; padding: 10px; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e293b; border-radius: 8px; margin-bottom: 10px; }}
            .mute-btn {{ background: #ef4444; border: none; color: white; padding: 8px 12px; border-radius: 5px; cursor: pointer; }}
            .timer {{ font-size: 16px; color: #f59e0b; margin: 5px 0; font-weight: bold; }}
            .current-call {{ font-size: 22px; color: #22c55e; margin: 10px 0; font-weight: bold; background: #1e293b; padding: 8px; border-radius: 6px; }}
            .spectator-banner {{ background: #b91c1c; color: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; font-weight: bold; font-size: 14px; display: {'block' if is_spectator else 'none'}; }}
            
            /* የቢንጎ ሰሌዳ አምዶች ዲዛይን (B:አረንጓዴ, I:ቀይ, N:ወሃ ሰማያዊ, G:ሰማያዊ, O:ብርቱካናማ) */
            .bingo-cell-b {{ background-color: #27ae60 !important; color: white; }}
            .bingo-cell-i {{ background-color: #c0392b !important; color: white; }}
            .bingo-cell-n {{ background-color: #5dade2 !important; color: white; }}
            .bingo-cell-g {{ background-color: #2980b9 !important; color: white; }}
            .bingo-cell-o {{ background-color: #d35400 !important; color: white; }}
            .bingo-cell-free {{ background-color: #f59e0b !important; color: #000; font-weight: bold; }}

            .card {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; max-width: 360px; margin: 15px auto; background: #334155; padding: 10px; border-radius: 10px; }}
            .col-header {{ font-weight: bold; font-size: 16px; padding: 5px; }}
            .cell {{ padding: 12px 2px; font-size: 16px; font-weight: bold; border-radius: 5px; cursor: pointer; transition: 0.2s; }}
            .cell.marked {{ border: 3px solid #facc15 !important; opacity: 0.85; }}
            .bingo-btn {{ background: #3b82f6; color: white; border: none; padding: 12px 25px; font-size: 16px; border-radius: 8px; cursor: pointer; margin-top: 10px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h3>EdilBingo ({'BigWin 50 ETB' if type=='bigwin' else 'የዘውትር 10 ETB'})</h3>
            <button class="mute-btn" id="muteBtn" onclick="toggleMute()">🔊 ድምፅ (ON)</button>
        </div>

        <div class="spectator-banner" id="spectatorBanner">
            ⚠️ የስፔክቴተር ሁነታ (Spectator Mode): ባላንስዎ ከ {min_req} በታች ስለሆነ መጫወት አይችሉም። ቁጥሮችን እና አሸናፊዎችን ብቻ መከታተል ይችላሉ!
        </div>

        <div class="timer" id="timerBox"></div>
        <div class="current-call" id="currentCallBox">የተጠራ ቁጥር: ገና አልጀመረም</div>
        
        <p id="cardStatusLabel">ካርድዎ (ቁጥር ሲጠራ ይንኩ):</p>

        <div class="card" id="bingoCard">
            <!-- ColumnHeaders & Cells generated via JS -->
        </div>

        <button class="bingo-btn" id="bingoBtn" onclick="checkBingoWin()">BINGO (አሸነፍኩ!)</button>

        <script>
            let isMuted = false;
            let calledNumbers = new Set();
            let cardMatrix = []; 
            let isSpectator = {'true' if is_spectator else 'false'};

            if (isSpectator) {{
                document.getElementById('bingoBtn').style.display = 'none';
                document.getElementById('cardStatusLabel').innerText = "የተመልካች ሰሌዳ (ቁጥሮች ሲጠሩ ማየት ይችላሉ):";
            }}

            function toggleMute() {{
                isMuted = !isMuted;
                document.getElementById('muteBtn').innerText = isMuted ? "🔇 ድምፅ (OFF)" : "🔊 ድምፅ (ON)";
            }}

            function speakNumber(text) {{
                if (isMuted) return;
                let utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'am-ET';
                window.speechSynthesis.speak(utterance);
            }}

            function getBingoClass(num) {{
                if (num === 'FREE') return 'bingo-cell-free';
                if (num >= 1 && num <= 15) return 'bingo-cell-b';
                if (num >= 16 && num <= 30) return 'bingo-cell-i';
                if (num >= 31 && num <= 45) return 'bingo-cell-n';
                if (num >= 46 && num <= 60) return 'bingo-cell-g';
                if (num >= 61 && num <= 75) return 'bingo-cell-o';
                return '';
            }}

            function getRandomUnique(min, max, count) {{
                let arr = [];
                while(arr.length < count) {{
                    let r = Math.floor(Math.random() * (max - min + 1)) + min;
                    if(!arr.includes(r)) arr.push(r);
                }}
                return arr.sort((a,b) => a - b);
            }}

            function generateCard() {{
                let colB = getRandomUnique(1, 15, 5);
                let colI = getRandomUnique(16, 30, 5);
                let colN = getRandomUnique(31, 45, 4);
                colN.splice(2, 0, 'FREE');
                let colG = getRandomUnique(46, 60, 5);
                let colO = getRandomUnique(61, 75, 5);

                let container = document.getElementById('bingoCard');
                container.innerHTML = '';

                let letters = ['B', 'I', 'N', 'G', 'O'];
                let headerColors = ['#27ae60', '#c0392b', '#5dade2', '#2980b9', '#d35400'];
                for(let i=0; i<5; i++) {{
                    let h = document.createElement('div');
                    h.className = 'col-header';
                    h.style.color = headerColors[i];
                    h.innerText = letters[i];
                    container.appendChild(h);
                }}

                cardMatrix = [];
                for (let r = 0; r < 5; r++) {{
                    let rowCols = [colB[r], colI[r], colN[r], colG[r], colO[r]];
                    let rowState = [];
                    for (let c = 0; c < 5; c++) {{
                        let val = rowCols[c];
                        let cell = document.createElement('div');
                        cell.className = 'cell ' + getBingoClass(val);
                        cell.innerText = val;

                        let isFree = (val === 'FREE');
                        rowState.push(isFree);

                        if (isFree) {{
                            cell.classList.add('marked');
                        }} else {{
                            let cellObj = {{ row: r, col: c, val: val, marked: false, element: cell }};
                            cell.onclick = function() {{
                                if (isSpectator) {{
                                    alert("⚠️ እርስዎ በስፔክቴተር (ተመልካች) ሁነታ ላይ ነዎት፤ ካርድ መምረጥ አይችሉም!");
                                    return;
                                }}
                                if (calledNumbers.has(val)) {{
                                    cellObj.marked = !cellObj.marked;
                                    cell.classList.toggle('marked');
                                    rowState[c] = cellObj.marked;
                                }} else {{
                                    alert("ይህ ቁጥር ገና አልተጠራም!");
                                }}
                            }};
                        }}
                        container.appendChild(cell);
                    }}
                    cardMatrix.push(rowState);
                }}
            }}

            generateCard();

            let allNumbers = getRandomUnique(1, 75, 75);
            let callIndex = 0;

            function startCalling() {{
                let callInterval = setInterval(() => {{
                    if (callIndex < allNumbers.length) {{
                        let num = allNumbers[callIndex];
                        calledNumbers.add(num);
                        
                        let letter = num <= 15 ? 'B' : num <= 30 ? 'I' : num <= 45 ? 'N' : num <= 60 ? 'G' : 'O';
                        let displayTxt = `የተጠራ: ${{letter}}-${{num}}`;
                        document.getElementById('currentCallBox').innerText = displayTxt;
                        speakNumber(letter + " " + num);
                        callIndex++;
                    }} else {{
                        clearInterval(callInterval);
                    }}
                }}, 3500);
            }}

            let timeLeft = "{'60' if type=='bigwin' else '5'}";
            let timerInterval = setInterval(() => {{
                if (timeLeft > 0) {{
                    document.getElementById('timerBox').innerText = "ጨዋታው የሚጀምርበት ቀሪ ሰዓት: " + timeLeft + " ሰከንድ";
                    timeLeft--;
                }} else {{
                    clearInterval(timerInterval);
                    document.getElementById('timerBox').innerText = "🎮 ጨዋታው በሂደት ላይ ነው!";
                    startCalling();
                }}
            }}, 1000);

            function checkBingoWin() {{
                if (isSpectator) return;
                let win = false;

                for (let r = 0; r < 5; r++) {{
                    if (cardMatrix[r][0] && cardMatrix[r][1] && cardMatrix[r][2] && cardMatrix[r][3] && cardMatrix[r][4]) {{
                        win = true;
                    }}
                }}

                for (let c = 0; c < 5; c++) {{
                    if (cardMatrix[0][c] && cardMatrix[1][c] && cardMatrix[2][c] && cardMatrix[3][c] && cardMatrix[4][c]) {{
                        win = true;
                    }}
                }}

                if (cardMatrix[0][0] && cardMatrix[1][1] && cardMatrix[2][2] && cardMatrix[3][3] && cardMatrix[4][4]) {{
                    win = true;
                }}
                if (cardMatrix[0][4] && cardMatrix[1][3] && cardMatrix[2][2] && cardMatrix[3][1] && cardMatrix[4][0]) {{
                    win = true;
                }}

                if (win) {{
                    alert("🎉 እንኳን ደስ አላችሁ! ትክክለኛ የቢንጎ መስመር ሞልተዋል (BINGO)!");
                }} else {{
                    alert("❌ እስካሁን ሙሉ አግድም፣ ቋሚ ወይም ዲያጎናል መስመር አልሞሉም! (ወይም ያልተጠራ ቁጥር መርጠዋል)");
                }}
            }}
        </script>
    </body>
    </html>
    """


# ቦቱን እና ሰርቨሩን በአንድ ላይ ማስጀመር
async def run_bot():
  await dp.start_polling(bot)


if __name__ == "__main__":
  import threading

  server_thread = threading.Thread(
      target=lambda: uvicorn.run(app, host="127.0.0.1", port=8000), daemon=True
  )
  server_thread.start()

  asyncio.run(run_bot())
