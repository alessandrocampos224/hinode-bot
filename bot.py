import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import BytesIO
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
    """Comando /start"""
    await update.message.reply_text(
        "👋 Olá! Eu sou o bot da Hinode.\n\n"
        "Me envie um link de qualquer página de produtos da Hinode e "
        "eu vou gerar um arquivo CSV com todas as informações.\n\n"
        "Exemplo: https://www.hinode.com.br/fragrancias/fragrancias-masculinas\n\n"
        "💡 Dica: Você pode me adicionar em grupos também!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    await update.message.reply_text(
        "ℹ️ Como me usar:\n\n"
        "1. Copie o link de uma página de produtos da Hinode\n"
        "2. Cole e envie aqui no chat\n"
        "3. Aguarde eu processar e enviar o arquivo CSV\n\n"
        "❓ Problemas comuns:\n"
        "- Certifique-se que o link é do site da Hinode\n"
        "- A página deve conter produtos listados\n"
        "- Aguarde alguns segundos para o processamento"
    )

async def scrape_hinode(url: str) -> pd.DataFrame:
    """Função que faz o scraping da página"""
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

        return pd.DataFrame(products)
    except Exception as e:
        logging.error(f"Erro ao fazer scraping: {e}")
        raise

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lidar com URLs enviadas"""
    url = update.message.text
    
    # Verificar se é uma URL da Hinode
    if not "hinode.com.br" in url.lower():
        await update.message.reply_text(
            "❌ Por favor, envie apenas links do site da Hinode."
        )
        return

    try:
        # Informar que começou o processo
        status_message = await update.message.reply_text(
            "🔄 Coletando informações dos produtos...\n"
            "Isso pode levar alguns segundos..."
        )

        # Fazer o scraping
        df = await scrape_hinode(url)

        if df.empty:
            await status_message.edit_text(
                "❌ Nenhum produto encontrado nesta página."
            )
            return

        # Criar arquivo CSV na memória
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_buffer.seek(0)

        # Nome do arquivo baseado na URL
        filename = "produtos_hinode.csv"
        if "fragrancias-masculinas" in url:
            filename = "fragrancias_masculinas.csv"
        elif "fragrancias-femininas" in url:
            filename = "fragrancias_femininas.csv"

        # Enviar o arquivo
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_buffer,
            filename=filename,
            caption=f"✅ Arquivo gerado com sucesso!\n"
                   f"📊 {len(df)} produtos encontrados."
        )

        await status_message.delete()

    except Exception as e:
        error_message = (
            f"❌ Ocorreu um erro ao processar sua solicitação:\n{str(e)}\n\n"
            "Por favor, verifique se o link está correto e tente novamente."
        )
        await status_message.edit_text(error_message)

def main():
    """Função principal do bot"""
    # Criar a aplicação
    application = Application.builder().token(TOKEN).build()

    # Adicionar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    # Iniciar o bot
    print("Bot iniciado!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
