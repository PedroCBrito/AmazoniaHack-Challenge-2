# Frontend — Extração de Documentos Ambientais

React, TypeScript e Vite conectados à API FastAPI existente.

## Executar

Use Node.js 22.12+ (ou uma versão mais recente compatível com Vite) e a API na porta 8000.

Se a API já roda no Docker, aplique os endpoints novos preservando o volume SQLite:

```powershell
# Na raiz do projeto
docker compose --env-file .env.local up -d --build --no-deps api
```

```powershell
cd Frontend
npm ci
npm run dev
```

Abra o endereço exibido pelo Vite (normalmente http://localhost:5173).

A configuração padrão funciona sem criar um arquivo de ambiente. Para mudar a API,
copie `.env.example` para `.env` e ajuste `API_PROXY_TARGET`.
Mantenha `VITE_API_BASE_URL=/api`: o proxy do Vite encaminha as requisições para a API
e evita problemas de CORS. Reinicie o Vite após alterar essas variáveis.
O antigo `VITE_USE_MOCK_API` não é mais utilizado; todas as telas consultam a API.

## Fluxo e dados

- Upload: `POST /extract`, multipart com o campo `image`, JPEG ou PNG até 15 MB
  (a configuração da API pode impor outro limite).
- Histórico: `GET /documents?limit=20&offset=0`, consultado novamente a cada abertura
  da tela. Inclui paginação, atualização, estados vazio/carregando/erro.
- Consulta: `GET /documents/{id}`. A URL `/documentos/{id}` permite recarregar
  ou reabrir os dados sem executar OCR/LLM novamente.
- A revisão exibe todos os campos, coordenadas, partes, referências, campos adicionais,
  confiança heurística, evidências, avisos e texto OCR.
- O SQLite mantém os resultados originais da extração. Correções e confirmações
  manuais na revisão são apenas locais; a API não possui endpoint de gravação de revisão.
- Imagens originais não são persistidas. A prévia fica disponível no fluxo do upload;
  ao abrir pelo histórico, a tela usa o texto OCR salvo.
- Registros anteriores à integração, ou com falha na LLM, aparecem como
  “OCR salvo · sem extração estruturada”. Não são preenchidos com dados fictícios.

## Contrato do histórico

`GET /documents` retorna `{ items, total, limit, offset }`, ordenado do mais recente
para o mais antigo. `limit` aceita 1–100 e `offset` é não negativo.
Cada item contém `id`, `image_basename`, `created_at` (UTC), `ocr_model`,
`status` (`extracted` ou `ocr_only`), `document_type`, `number` e `municipality`.
O detalhe acrescenta `ocr` e `extraction` (nulo nos registros apenas com OCR).
A extração inclui `_meta.document_id`; o restante do contrato de `/extract` é preservado.

## Verificação

```powershell
npm run build
npm run lint
# Instale o navegador uma vez, ou use um Chrome/Edge já instalado:
npx playwright install chromium
npm run test:e2e
# Alternativa no Windows:
$env:PLAYWRIGHT_CHANNEL = 'msedge'
npm run test:e2e
```

Os testes de navegador iniciam o frontend na porta 5174 e uma API isolada na 8011,
com SQLite em memória e substitutos de OCR/LLM. Requerem Python com
`requirements-dev.txt` instalado na raiz. Não usam o banco nem a inferência em execução.
Cobrem upload multipart, exibição dos campos, recarga, histórico e falhas do serviço.

Na raiz, execute `python -m pytest -q` para testar a API, incluindo persistência
após reinicialização, compatibilidade com bancos antigos e paginação.

## Publicação

`npm run build` gera `dist/`. Configure o servidor que hospeda esses arquivos para
encaminhar `/api/*` à FastAPI removendo o prefixo `/api`, e para servir `index.html`
nas rotas do frontend, inclusive `/documentos/{id}`. O proxy do Vite existe apenas
em desenvolvimento e em `npm run preview`; ele não acompanha os arquivos estáticos.
