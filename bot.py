import os
import sys
import re
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO, BytesIO
import logging
from dotenv import load_dotenv
import time

# Carregar variáveis de ambiente
load_dotenv()

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
}

def clean_text(text):
    """Limpa e formata o texto removendo espaços extras e caracteres especiais"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    text = text.replace('\n', ' ').replace('\r', '')
    return text

def format_price(price):
    """Formata o preço para um formato consistente"""
    if not price:
        return "Preço não disponível"
    price = re.sub(r'[^\d,.]', '', price)
    if ',' in price and '.' in price:
        price = price.replace('.', '').replace(',', '.')
    elif ',' in price:
        price = price.replace(',', '.')
    try:
        return f"R$ {float(price):.2f}"
    except:
        return price

def extract_product_info(url: str, soup: BeautifulSoup) -> dict:
    """Extrai informações detalhadas de um produto"""
    try:
        # Nome do produto - tentando vários seletores possíveis
        name_selectors = [
            '.page-title span',
            'h1.page-title',
            '.product-info-main .product-name',
            '[data-ui-id="page-title-wrapper"]'
        ]
        name = None
        for selector in name_selectors:
            name = soup.select_one(selector)
            if name:
                break
        name = clean_text(name.text) if name else ""

        # Preço do produto - tentando vários seletores
        price_selectors = [
            '.price-final_price .price',
            '.special-price .price',
            '[data-price-type="finalPrice"] .price'
        ]
        price = None
        for selector in price_selectors:
            price = soup.select_one(selector)
            if price:
                break
        price = format_price(price.text) if price else "Preço não disponível"

        # Código/SKU
        sku_selectors = [
            '[itemprop="sku"]',
            '.product.attribute.sku .value',
            '[data-th="SKU"]'
        ]
        sku = None
        for selector in sku_selectors:
            sku = soup.select_one(selector)
            if sku:
                break
        sku = clean_text(sku.text) if sku else ""

        # Descrição
        desc_selectors = [
            '[itemprop="description"]',
            '.description .value',
            '.product.attribute.description'
        ]
        description = None
        for selector in desc_selectors:
            description = soup.select_one(selector)
            if description:
                break
        description = clean_text(description.text) if description else ""

        # Imagem
        img_selectors = [
            '.gallery-placeholder img',
            '[data-gallery-role="gallery-placeholder"] img',
            '.product.media img'
        ]
        image = None
        for selector in img_selectors:
            image = soup.select_one(selector)
            if image:
                break
        image_url = image['src'] if image and 'src' in image.attrs else ""

        # Debug log
        logger.info(f"Nome encontrado: {name}")
        logger.info(f"Preço encontrado: {price}")
        logger.info(f"SKU encontrado: {sku}")
        logger.info(f"Imagem encontrada: {image_url}")

        product = {
            "Nome": name,
            "Preço": price,
            "Código (SKU)": sku,
            "Descrição": description,
            "Link da Imagem": image_url,
            "Link do Produto": url
        }

        return product

    except Exception as e:
        logger.error(f"Erro ao extrair produto: {e}")
        logger.error("HTML da página:")
        logger.error(soup.prettify()[:500])  # Primeiros 500 caracteres do HTML para debug
        return None

def extract_category_products(url: str, soup: BeautifulSoup) -> list:
    """Extrai produtos de uma página de categoria"""
    products = []

    # Tenta encontrar a lista de produtos
    product_items = soup.select('.products-grid .product-item, .product-items .product-item')

    for item in product_items:
        try:
            # Nome e Link
            name_elem = item.select_one('.product-item-link')
            name = clean_text(name_elem.text) if name_elem else ""
            link = name_elem['href'] if name_elem and 'href' in name_elem.attrs else ""

            # Preço
            price_elem = item.select_one('.price-wrapper .price')
            price = format_price(price_elem.text) if price_elem else "Preço não disponível"

            # Código/SKU
            sku_elem = item.select_one('[data-product-id]')
            sku = sku_elem['data-product-id'] if sku_elem else ""

            # Imagem
            image_elem = item.select_one('.product-image-photo')
            image_url = image_elem['src'] if image_elem and 'src' in image_elem.attrs else ""

            product = {
                "Nome": name,
                "Preço": price,
                "Código (SKU)": sku,
                "Link da Imagem": image_url,
                "Link do Produto": link,
                "Descrição": ""  # Descrição vazia para produtos em lista
            }

            products.append(product)
            logger.info(f"Produto de categoria encontrado: {name}")

        except Exception as e:
            logger.error(f"Erro ao processar produto da categoria: {e}")
            continue

    return products

def scrape_hinode(url: str) -> list:
    """Função principal de scraping"""
    try:
        logger.info(f"Iniciando scraping da URL: {url}")

        # Adiciona um pequeno delay
        time.sleep(2)

        session = requests.Session()

        # Primeiro acessa a página inicial
        session.get("https://www.hinode.com.br", headers=HEADERS, timeout=30)

        # Depois acessa a página do produto
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        if '/p' in url or soup.select_one('.product-info-main'):
            product = extract_product_info(url, soup)
            return [product] if product else []
        else:
            return extract_category_products(url, soup)

    except Exception as e:
        logger.error(f"Erro no scraping: {e}")
        return []

def create_csv(products: list) -> BytesIO:
    """Cria arquivo CSV com os produtos"""
    try:
        if not products:
            return None

        output = StringIO()

        # Definir ordem das colunas
        fieldnames = [
            "Nome",
            "Preço",
            "Código (SKU)",
            "Descrição",
            "Link da Imagem",
            "Link do Produto"
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for product in products:
            # Garantir que todos os campos existem
            row = {field: product.get(field, "") for field in fieldnames}
            writer.writerow(row)

        return BytesIO(output.getvalue().encode('utf-8'))
    except Exception as e:
        logger.error(f"Erro ao criar CSV: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! Eu sou o bot da Hinode.\n\n"
        "Me envie um link de qualquer página de produtos da Hinode e "
        "eu vou gerar um arquivo CSV com todas as informações.\n\n"
        "Exemplo: https://www.hinode.com.br/fragrancias/fragrancias-masculinas"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

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

        await message.delete()

    except Exception as e:
        logger.error(f"Erro ao processar URL: {e}")
        await message.edit_text(f"❌ Erro ao processar. Por favor, tente novamente.")

def main():
    # Iniciar o bot
    application = Application.builder().token(TOKEN).build()

    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # Iniciar o polling
    print("Bot iniciado!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
