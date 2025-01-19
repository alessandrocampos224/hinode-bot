import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from fastapi import FastAPI, Request
import uvicorn

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Configurações
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Token não encontrado!")
    sys.exit(1)

# Headers para requisições
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Criar app FastAPI
app = FastAPI()

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
        logger.info(f"Iniciando scraping da URL: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        products = []

        # Tentar diferentes seletores para encontrar produtos
        selectors = [
            '.products.list.items.product-items .item.product',
            '.product.media',
            '.product-item-info',
            '[data-product-id]'
        ]

        found_products = []
        for selector in selectors:
            found_products = soup.select(selector)
            if found_products:
                logger.info(f"Encontrados {len(found_products)} produtos usando seletor: {selector}")
                break

        if not found_products:
            logger.warning("Nenhum produto encontrado com os seletores padrão")
            # Tentar página de produto único
            product_title = soup.select_one('.page-title span')
            if product_title:
                logger.info("Encontrado produto único")
                found_products = [soup]

        for product in found_products:
            try:
                # Tentar diferentes seletores para cada informação
                name = (
                    product.select_one('.product-item-name') or 
                    product.select_one('.page-title span') or 
                    product.select_one('.product-item-link')
                )

                price = (
                    product.select_one('.price') or 
                    product.select_one('.price-wrapper') or 
                    product.select_one('[data-price-type="finalPrice"]')
                )

                image = (
                    product.select_one('img.product-image-photo') or 
                    product.select_one('.product.photo.product-item-photo img') or
                    product.select_one('.gallery-placeholder img')
                )

                link = (
                    product.select_one('.product-item-link') or 
                    product.select_one('.product.photo.product-item-photo') or
                    soup.select_one('link[rel="canonical"]')
                )

                if name:
                    name_text = name.get_text().strip()
                    price_text = price.get_text().strip() if price else "Preço não disponível"
                    image_url = image['src'] if image and image.has_attr('src') else ""
                    product_link = ""
                    
                    if link:
                        if link.has_attr('href'):
                            product_link = link['href']
                        elif link.has_attr('content'):
                            product_link = link['content']

                    product_data = {
                        "Nome": name_text,
                        "Preço": price_text,
                        "Imagem": image_url,
                        "Link": product_link
                    }
                    
                    products.append(product_data)
                    logger.info(f"Produto processado: {name_text}")

            except Exception as e:
                logger.error(f"Erro ao processar produto individual: {e}")
                continue

        return products

    except Exception as e:
        logger.error(f"Erro durante o scraping: {e}")
        raise

def create_csv(products: list) -> BytesIO:
    try:
        if not products:
            logger.warning("Nenhum produto para criar CSV")
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
    logger.info(f"Recebido URL: {url}")
    
    if not "hinode.com.br" in url.lower():
        await update.message.reply_text("❌ Por favor, envie apenas links do site da Hinode.")
        return

    try:
        message = await update.message.reply_text("🔄 Coletando produtos...")
        logger.info("Iniciando coleta de produtos")
        
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
        logger.info("CSV enviado com sucesso")
        
        await message.delete()

    except Exception as e:
        logger.error(f"Erro ao processar URL: {e}")
        error_msg = f"❌ Erro ao processar: {str(e)}"
        try:
            await message.edit_text(error_msg)
        except:
            await update.message.reply_text(error_msg)

# Inicialização do bot
bot = Application.builder().token(TOKEN).build()

async def setup_bot():
    """Configurar o bot com seus handlers"""
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    await bot.initialize()
    logger.info("Bot configurado com sucesso!")

@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    """Manipular atualizações do Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot.bot)
        await bot.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return {"status": "error", "message": str(e)}

@app.on_event("startup")
async def on_startup():
    """Configurar webhook quando a aplicação iniciar"""
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')}/webhook/{TOKEN}"
    await setup_bot()
    await bot.bot.set_webhook(webhook_url)
    logger.info(f"Webhook configurado para: {webhook_url}")

@app.get("/")
async def root():
    """Rota de teste"""
    return {"status": "Bot está rodando!"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
