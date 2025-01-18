import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

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

async def scrape_hinode(url: str) -> list:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        products = []

        # Buscar produtos na página
        for product in soup.select('li.item.product.product-item'):
            try:
                name = product.select_one('.product-item-link')
                price = product.select_one('.price')
                image = product.select_one('img.product-image-photo')
                link = product.select_one('a.product-item-link')
                sku = product.select_one('[data-product-id]')
                description = product.select_one('.product-item-description')

                products.append({
                    "Nome": name.text.strip() if name else "Nome não encontrado",
                    "Preço": price.text.strip() if price else "Preço não disponível",
                    "Código (SKU)": sku['data-product-id'] if sku else "",
                    "Descrição": description.text.strip() if description else "",
                    "Link da Imagem": image['src'] if image else "",
                    "Link do Produto": link['href'] if link else ""
                })
            except Exception as e:
                logging.error(f"Erro ao processar produto: {e}")
                continue

        return products
    except Exception as e:
        logging.error(f"Erro ao fazer scraping: {e}")
        raise

def create_csv(products: list) -> BytesIO:
    """Criar arquivo CSV na memória"""
    output = StringIO()
    if products:
        writer = csv.DictWriter(output, fieldnames=products[0].keys())
        writer.writeheader()
        writer.writerows(products)
    
    # Converter para BytesIO com BOM para UTF-8
    return BytesIO(('\ufeff' + output.getvalue()).encode('utf-8'))

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    if not "hinode.com.br" in url.lower():
        await update.message.reply_text(
            "❌ Por favor, envie apenas links do site da Hinode."
        )
        return

    try:
        status_message = await update.message.reply_text(
            "🔄 Coletando informações dos produtos..."
        )

        products = await scrape_hinode(url)

        if not products:
            await status_message.edit_text(
                "❌ Nenhum produto encontrado nesta página."
            )
            return

        csv_buffer = create_csv(products)
        filename = "produtos_hinode.csv"

        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_buffer,
            filename=filename,
            caption=f"✅ Arquivo gerado com sucesso!\n"
                   f"📊 {len(products)} produtos encontrados."
        )

        await status_message.delete()

    except Exception as e:
        error_message = (
            f"❌ Erro ao processar sua solicitação:\n{str(e)}\n\n"
            "Verifique se o link está correto e tente novamente."
        )
        await status_message.edit_text(error_message)

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("Bot iniciado!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
