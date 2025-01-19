import os
import sys
import re
from urllib.parse import urlparse, unquote
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
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

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Token não encontrado!")
    sys.exit(1)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive'
}

app = FastAPI()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Eu sou o bot da Hinode.\n\n"
        "Me envie um link de qualquer página de produtos da Hinode e "
        "eu vou gerar um arquivo CSV com todas as informações.\n\n"
        "Exemplo: https://www.hinode.com.br/fragrancias/fragrancias-masculinas"
    )

def extract_product_info(url: str) -> dict:
    """Extrai informações de um produto da página"""
    try:
        logger.info(f"Extraindo informações da URL: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Extrair dados usando regex
        name_match = re.search(r'<h1[^>]*class="[^"]*page-title[^"]*"[^>]*>.*?<span>(.*?)</span>', response.text)
        price_match = re.search(r'<span[^>]*class="[^"]*price[^"]*"[^>]*>(R?\$?\s*[\d,.]+)', response.text)
        image_match = re.search(r'<img[^>]*class="[^"]*gallery-placeholder__image[^"]*"[^>]*src="([^"]*)"', response.text)
        sku_match = re.search(r'data-product-id="(\d+)"', response.text)
        desc_match = re.search(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', response.text, re.DOTALL)

        product = {
            "Nome": unquote(name_match.group(1).strip()) if name_match else "Nome não encontrado",
            "Preço": price_match.group(1).strip() if price_match else "Preço não disponível",
            "Código": sku_match.group(1) if sku_match else "",
            "Imagem": image_match.group(1) if image_match else "",
            "Link": url,
            "Descrição": desc_match.group(1).strip() if desc_match else ""
        }

        logger.info(f"Produto encontrado: {product['Nome']}")
        return product
    except Exception as e:
        logger.error(f"Erro ao extrair informações: {e}")
        return None

def extract_products_from_category(url: str) -> list:
    """Extrai informações de produtos de uma página de categoria"""
    try:
        logger.info(f"Extraindo produtos da categoria: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Extrair links dos produtos
        product_links = re.findall(r'<a[^>]*class="[^"]*product-item-link[^"]*"[^>]*href="([^"]*)"', response.text)
        
        products = []
        for link in product_links[:10]:  # Limitar a 10 produtos por vez
            try:
                product = extract_product_info(link)
                if product:
                    products.append(product)
            except Exception as e:
                logger.error(f"Erro ao processar produto {link}: {e}")
                continue
                
        return products
    except Exception as e:
        logger.error(f"Erro ao extrair produtos da categoria: {e}")
        return []

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
        
        # Verifica se é uma página de produto ou categoria
        if '/p' in url:
            product = extract_product_info(url)
            products = [product] if product else []
        else:
            products = extract_products_from_category(url)

        if not products:
            await message.edit_text("❌ Nenhum produto encontrado. Tente um link diferente.")
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
        logger.error(f"Erro ao processar URL: {e}")
        await message.edit_text(f"❌ Erro ao processar. Por favor, tente novamente.")

# Configuração do bot e webhook
bot = Application.builder().token(TOKEN).build()

async def setup_bot():
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    await bot.initialize()
    logger.info("Bot configurado com sucesso!")

@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
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
    webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')}/webhook/{TOKEN}"
    await setup_bot()
    await bot.bot.set_webhook(webhook_url)
    logger.info(f"Webhook configurado para: {webhook_url}")

@app.get("/")
async def root():
    return {"status": "Bot está rodando!"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
