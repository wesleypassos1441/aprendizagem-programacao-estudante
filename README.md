# Automação Anhanguera / AVA

Projeto inicial em Python + Playwright para:

1. entrar em `login.anhanguera.com`;
2. autenticar com CPF e senha;
3. fechar o comunicado inicial;
4. abrir a área **Estudar**;
5. escolher uma disciplina;
6. perguntar a unidade desejada;
7. perguntar se deve abrir **Atividade de Aprendizagem** ou **Avaliação da Unidade**.
8. ao abrir a primeira questão, capturar o enunciado e as alternativas e enviá-los ao Gemini em modo tutor para exibir uma explicação no terminal.

## Preparação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

O sistema sempre pede CPF, senha e API key Gemini no terminal a cada execução.
Não salve CPF, senha ou API key no `.env`, especialmente se for compartilhar a pasta com outras pessoas.
Se a chave atual atingir cota durante o uso, o script pergunta por uma nova chave e continua a mesma sessão sem fechar o navegador.

Opcionalmente, configure apenas opções não sensíveis no `.env`, como `GEMINI_MODELS`, por exemplo:

```env
GEMINI_MODELS=gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.5-pro
```

O script tenta os modelos nessa ordem quando um deles estiver temporariamente indisponível ou com cota esgotada.

## Execução

```powershell
python main.py
```

Por padrão, o navegador abre visível para facilitar o refinamento dos seletores.

## Observação importante

Como páginas web mudam com frequência, esta primeira versão já traz seletores com fallback e mensagens de diagnóstico. O próximo passo natural é executar o fluxo uma vez e ajustar os seletores reais que aparecerem na sua conta.
