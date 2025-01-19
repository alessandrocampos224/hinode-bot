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

# Funções do bot
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

        logger.info("Iniciando busca por produtos na página")
    # Primeiro tenta o layout da página de categoria
    products_elements = soup.select('.products.list.items.product-items .item.product')
    
    # Se não encontrar, tenta o layout da página de produto único
    if not products_elements:
        products_elements = [soup.select_one('.product-info-main')]
        logger.info("Usando layout de produto único")
    
    logger.info(f"Encontrados {len(products_elements)} elementos de produto")

    for product in products_elements:
        if not product:
            continue
            
        try:
            # Tenta diferentes seletores para o nome
            name = (product.select_one('.product-item-name') or 
                   product.select_one('.page-title') or 
                   product.select_one('[itemprop="name"]'))
            
            # Tenta diferentes seletores para o preço
            price = (product.select_one('.price') or 
                    product.select_one('[data-price-type="finalPrice"]'))
            
            # Tenta diferentes seletores para a imagem
            image = (product.select_one('img.product-image-photo') or 
                    soup.select_one('.gallery-placeholder img'))
            
            # Tenta diferentes seletores para o link
            link = (product.select_one('.product-item-link') or 
                   soup.select_one('link[rel="canonical"]'))
            
            # Tenta diferentes seletores para o SKU
            sku = (product.select_one('[data-product-id]') or 
                  product.select_one('.product.attribute.sku .value'))

                # Extrai e limpa os dados
                nome_texto = name.get_text().strip() if name else None
                if nome_texto:
                    # Extrai preço
                    preco_texto = price.get_text().strip() if price else "Preço não disponível"
                    
                    # Extrai SKU/Código
                    codigo = ""
                    if sku:
                        if sku.has_attr('data-product-id'):
                            codigo = sku['data-product-id']
                        else:
                            codigo = sku.get_text().strip()
                    
                    # Extrai imagem
                    imagem_url = ""
                    if image:
                        if image.has_attr('src'):
                            imagem_url = image['src']
                        elif image.has_attr('data-src'):
                            imagem_url = image['data-src']
                    
                    # Extrai link
                    link_url = ""
                    if link:
                        if link.has_attr('href'):
                            link_url = link['href']
                        elif link.has_attr('content'):
                            link_url = link['content']
                    
                    # Adiciona o produto à lista
                    products.append({
                        "Nome": nome_texto,
                        "Preço": preco_texto,
                        "Código": codigo,
                        "Imagem": imagem_url,
                        "Link": link_url
                    })
                    logger.info(f"Produto processado: {nome_texto}")
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
