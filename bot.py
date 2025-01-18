import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token do bot
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Headers para a requisição
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Eu sou o bot da Hinode.\n\n"
        "Me envie um link de qualquer página de produtos da Hinode e "
        "eu vou gerar um arquivo CSV com todas as informações.\n\n"
        "Exemplo: https://www.hinode.com.br/fragrancias/fragrancias-masculinas"
    )

def scrape_hinode(url: str) -> list:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'lxml')
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
            logging.error(f"Erro ao processar produto: {e}")
            continue

    return products

def create_csv(products: list) -> BytesIO:
    if not products:
        return None
        
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=products[0].keys())
    writer.writeheader()
    writer.writerows(products)
    
    return BytesIO(output.getvalue().encode('utf-8'))

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
        await message.edit_text(f"❌ Erro: {str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Bot iniciado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
