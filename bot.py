import os
import sys
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from fastapi import FastAPI, Request
import uvicorn
import random

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

# Headers para simular um navegador real
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
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
        
        # Adicionar delay aleatório
        time.sleep(random.uniform(1, 3))
        
        session = requests.Session()
        # Primeiro faz uma requisição para a página inicial
        session.get("https://www.hinode.com.br", headers=HEADERS, timeout=30)
        
        # Adiciona referrer nos headers
        HEADERS['Referer'] = 'https://www.hinode.com.br'
        
        # Faz a requisição para a URL do produto
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        logger.info(f"Status da resposta: {response.status_code}")
        logger.info(f"Tamanho da resposta: {len(response.text)} bytes")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        products = []

        # Debug: salvar HTML para análise
        logger.info("Primeiros 500 caracteres do HTML:")
        logger.info(response.text[:500])

        # Tentar diferentes padrões de estrutura
        product_elements = (
            soup.select('.product-items .product-item') or
            soup.select('.products-grid .product-item') or
            soup.select('.category-products .item') or
            [soup.select_one('.product-info-main')] # Para página de produto único
        )

        if not product_elements or all(x is None for x in product_elements):
            logger.warning("Nenhum produto encontrado nos seletores principais")
            # Tentar encontrar qualquer elemento com preço
            price_elements = soup.select('[data-price-type], .price')
            if price_elements:
                for price_elem in price_elements:
                    parent = price_elem.find_parent('.product-item') or price_elem.find_parent('.item')
                    if parent and parent not in product_elements:
                        product_elements.append(parent)

        logger.info(f"Encontrados {len(product_elements)} elementos de produto")

        for product in product_elements:
            if not product:
                continue

            try:
                # Busca por diferentes padrões de elementos
                name_elem = (
                    product.select_one('.product-name') or
                    product.select_one('.product-item-name') or
                    product.select_one('.page-title .base') or
                    product.select_one('.product-item-link')
                )

                price_elem = (
                    product.select_one('.special-price .price') or
                    product.select_one('.normal-price .price') or
                    product.select_one('.price-wrapper .price') or
                    product.select_one('.price')
                )

                img_elem = (
                    product.select_one('.product-image-photo') or
                    product.select_one('.photo img') or
                    product.select_one('img[data-role="product-image"]')
                )

                link_elem = (
                    product.select_one('.product-item-link') or
                    product.select_one('.product-image')
                )

                if name_elem:
                    name = name_elem.get_text().strip()
                    price = price_elem.get_text().strip() if price_elem else "Preço não disponível"
                    image = img_elem.get('src') if img_elem else ""
                    link = link_elem.get('href') if link_elem else url

                    product_data = {
                        "Nome": name,
                        "Preço": price,
                        "Imagem": image,
                        "Link": link
                    }

                    logger.info(f"Produto encontrado: {name}")
                    products.append(product_data)

            except Exception as e:
                logger.error(f"Erro ao processar produto individual: {e}")
                continue

        logger.info(f"Total de produtos processados: {len(products)}")
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
