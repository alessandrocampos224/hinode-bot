import os
import sys
import asyncio
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from dotenv import load_dotenv
from flask import Flask

# Criar app Flask
app = Flask(__name__)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

# Token do bot
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Token não encontrado!")
    sys.exit(1)

# Headers para a requisição
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

@app.route('/')
def home():
    return 'Bot está rodando!'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "👋 Olá! Eu sou o bot da Hinode.\n\n"
            "Me envie um link de qualquer página de produtos da Hinode e "
            "eu vou gerar um arquivo CSV com todas as informações.\n\n"
            "Exemplo: https://www.hinode.com.br/fragrancias/fragrancias-masculinas"
        )
    except Exception as e:
        logger.error(f"Erro no comando start: {e}")

def scrape_hinode(url: str) -> list:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        products = []

        for product in soup.select('li.item.product.product-item'):
            try:
                name = product.select_one('.product-item-link')
                price = product.select_one('.price')
                image = product.select_one('img.product-image-photo')
                link = product.select_one('a.product-item-link')
                sku = product.select_one('[data-product-id]')

                if name:
                    products.append({
                        "Nome": name.text.strip(),
                        "Preço": price.text.strip() if price else "Preço não disponível",
                        "Código": sku['data-product-id'] if sku else "",
                        "Imagem": image['src'] if image else "",
                        "Link": link['href'] if link else ""
                    })
            except Exception as e:
                logger.error(f"Erro ao processar produto: {e}")
                continue

        return products
    except Exception as e:
        logger.error(f"Erro no scraping: {e}")
        raise

def create_csv(products: list) -> BytesIO:
    try:
        if not products:
            return None
            
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=products[0].keys())
        writer.writeheader()
        writer.writerows(products)
        
        return BytesIO(output.getvalue().encode('utf-8'))
    except Exception as e:
        logger.error(f"Erro ao criar CSV: {e}")
        return None

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not "hinode.com.br" in url.lower():
        await update.message.reply_text("❌ Por favor, envie apenas links do site da Hinode.")
        return

    try:
        message = await update.message.reply_text("🔄 Coletando produtos...")
        
        products = scrape_hinode(url)
        if not products:
            await message.edit_text("❌ Nenhum produto encontrado.")
            return

        csv_file = create_csv(products)
        if not csv_file:
            await message.edit_text("❌ Erro ao gerar arquivo.")
            return

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_file,
            filename="produtos_hinode.csv",
            caption=f"✅ Concluído! {len(products)} produtos encontrados."
        )
        
        await message.delete()

    except Exception as e:
        error_msg = f"❌ Erro ao processar: {str(e)}"
        try:
            await message.edit_text(error_msg)
        except:
            await update.message.reply_text(error_msg)

async def run_bot():
    try:
        # Iniciar o bot
        application = Application.builder().token(TOKEN).build()
        
        # Adicionar handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        
        # Iniciar o polling
        await application.initialize()
        await application.start()
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Erro ao iniciar o bot: {e}")
        sys.exit(1)

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Criar thread para o Flask
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Iniciar o bot no thread principal
    asyncio.run(run_bot())
