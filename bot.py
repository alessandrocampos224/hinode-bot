import os
import sys
import json
from urllib.parse import urlparse, parse_qs
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

# Configurações
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("Token não encontrado!")
    sys.exit(1)

# Headers para API
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Store': 'hinode',
    'Content-Type': 'application/json'
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

def get_product_info(url: str) -> list:
    try:
        logger.info(f"Obtendo informações do produto: {url}")
        
        # Se for página de produto único
        if '/p' in url:
            # Extrair SKU da URL
            path = urlparse(url).path
            sku = path.split('/')[-2] if path.endswith('/p') else path.split('/')[-1]
            
            # URL da API de produto
            api_url = f"https://api.hinode.com.br/v2/products/{sku}"
            response = requests.get(api_url, headers=HEADERS)
            
            if response.status_code == 200:
                product_data = response.json()
                return [{
                    "Nome": product_data.get('name', 'Nome não disponível'),
                    "Preço": f"R$ {product_data.get('price', 0):.2f}",
                    "Código": product_data.get('sku', ''),
                    "Descrição": product_data.get('description', ''),
                    "Imagem": product_data.get('image', {}).get('url', ''),
                    "Link": url
                }]
        
        # Se for página de categoria
        else:
            # Extrair categoria da URL
            category = urlparse(url).path.split('/')[-1]
            
            # URL da API de categoria
            api_url = f"https://api.hinode.com.br/v2/categories/{category}/products"
            params = {
                "page": 1,
                "pageSize": 48,
                "sort": "relevance"
            }
            
            response = requests.get(api_url, headers=HEADERS, params=params)
            
            if response.status_code == 200:
                category_data = response.json()
                products = category_data.get('items', [])
                
                return [{
                    "Nome": product.get('name', 'Nome não disponível'),
                    "Preço": f"R$ {product.get('price', 0):.2f}",
                    "Código": product.get('sku', ''),
                    "Descrição": product.get('shortDescription', ''),
                    "Imagem": product.get('image', {}).get('url', ''),
                    "Link": f"https://www.hinode.com.br/{product.get('url', '')}"
                } for product in products]
        
        return []
    except Exception as e:
        logger.error(f"Erro ao obter informações do produto: {e}")
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
        
        products = get_product_info(url)
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
