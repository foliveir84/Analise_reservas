# Design: Suporte a PDF no upload das Reservas

**Data:** 2026-06-18
**Estado:** Aprovado por design (pendente validação final do utilizador)

## 1. Objetivo

Permitir que o utilizador faça upload de PDF (além do Excel já suportado) na aplicação
Streamlit. Quando o ficheiro carregado é PDF, o `parse_reservas.py` é usado como módulo
para extrair os registos e devolver um `pandas.DataFrame` compatível com o pipeline
existente do `main.py`, sem alterar o comportamento das análises.

## 2. Contexto

- `main.py:47` aceita hoje apenas `type=["xlsx","xls"]` e lê com
  `pd.read_excel(ficheiro, skiprows=17)`, mantendo as colunas
  `['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']`.
- `parse_reservas.py` já existe e converte PDF → CSV (CLI standalone) usando
  `pdfplumber.extract_words` com colunas ancoradas em `N.º Reserva`.
- Bug de compatibilidade identificado: `parse_reservas.py:42` emite
  `"Dt.Criação"` (sem espaço após o ponto), enquanto o `main.py` espera
  `"Dt. Criação"` (com espaço). A correção faz parte deste trabalho.

## 3. Arquitetura / Componentes

### 3.1 `parse_reservas.py` (módulo reutilizável)

- Mantém toda a lógica de parsing atual (CLI standalone inalterado).
- **Correção:** `REQUESTED_HEADER` passa de `"Dt.Criação"` para `"Dt. Criação"`
  (com espaço), alinhando com o esperado pelo `main.py`.
- **Nova função utilitária:** `to_dataframe(records, fields=REQUESTED, header=REQUESTED_HEADER)`:
  - Recebe `records` (lista de dicts devolvida por `parse_pdf`).
  - Devolve `pandas.DataFrame` com colunas `REQUESTED_HEADER`, na mesma ordem.
  - Renomeia os campos internos (`REQUESTED`) para o cabeçalho legível.
  - Devolve `Dt. Criação` como `str` (a conversão para `datetime` é feita no
    `main.py`, como já acontece para o Excel).
  - Devolve `Qtd. Res.` como tipo numérico (int/float conforme valores).
  - Coalesce de valores em falta para `""` / `NaN` conforme o tipo.
- A função fica disponível para importação: `from parse_reservas import parse_pdf, to_dataframe`.

### 3.2 `main.py` (Streamlit)

- `st.file_uploader` passa a `type=["xlsx", "xls", "pdf"]`.
- Deteta o tipo pela extensão de `ficheiro.name` (case-insensitive).
- **Ramo Excel (inalterado):** `pd.read_excel(ficheiro, skiprows=17)` + seleção
  das 5 colunas — caminho original mantido.
- **Ramo PDF (novo):**
  1. Escrever o conteúdo carregado num `tempfile.NamedTemporaryFile(suffix='.pdf',
     delete=False)` (necessário porque `pdfplumber.open` requer path no disco).
     Em Windows, `NamedTemporaryFile` com `delete=False` evita problemas de
     "ficheiro em uso".
  2. Importar `from parse_reservas import parse_pdf, to_dataframe` e chamar
     `records = parse_pdf(tmp_path)`.
  3. `df = to_dataframe(records)`.
  4. Limpar o ficheiro temporário (num bloco `try/finally`).
  5. A partir daqui, o resto do pipeline (filtro Faturada, agrupamentos,
     pivot, styled_df) corre inalterado sobre `df`.
- **Erros:** `st.error` + `st.stop()` quando:
  - PDF não produzir registos (`len(records) == 0`).
  - Extensão não for reconhecida (defensivo; o `type=` do Streamlit já filtra).

### 3.3 `requirements.txt`

- Adicionar `pdfplumber==0.11.4` (compatível com o resto do stack).

## 4. Fluxo de dados

```
Upload (xlsx | xls | pdf)
   ├── xlsx/xls → pd.read_excel(skiprows=17) → df[5 colunas]
   └── pdf      → tempfile.pdf → parse_pdf() → records → to_dataframe()
                     ↓
   df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])   (resto inalterado)
   → filtro Faturada → agrupamento → pivot → styled_df
```

Os dois ramos convergem no mesmo `df` com as colunas:
`['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']`.

## 5. Tratamento de erros

- **PDF sem registos / sem palavras extraídas:**
  `st.error("Não foi possível extrair registos do PDF. Verifique que o ficheiro é uma exportação válida da LISTAGEM DE RESERVAS.")` + `st.stop()`.
- **Registos com CNP/Produto em falta:** os avisos continuam a ir para
  `sys.stderr` (já existe no parser). Manter comportamento; opcionalmente
  expor via `st.warning` se o utilizador quiser visibilidade — não incluído
  no âmbito por defeito.
- **Extensão não suportada (defensivo):** `st.error("Tipo de ficheiro não suportado.")` + `st.stop()`.
- **Falta de `pdfplumber`:** a dependência é adicionada ao `requirements.txt`;
  a importação no topo do `main.py` (dentro do ramo PDF, para não quebrar o
  ramo Excel) falha graciosamente com `st.error` caso o import não esteja disponível.
- **Limpeza do ficheiro temporário:** sempre executada em `finally`, mesmo
  em caso de erro.

## 6. Decisões de implementação

- **Importação tardia do `parse_reservas` e `pdfplumber`:** feita dentro do
  ramo PDF (não no topo do `main.py`) para não obrigar a instalar
  `pdfplumber` quando o utilizador só usa Excel. Permite que o ramo Excel
  continue a funcionar mesmo se a dependência PDF estiver em falta.
- **`to_dataframe` fica no `parse_reservas.py`:** centraliza a conversão
  records→DataFrame, útil também para outros consumidores futuros e para
  testes isolados do módulo.
- **Cabeçalho corrigido no parser (não no main.py):** o CSV reduzido
  produzido pelo CLI fica também compatível com o `main.py`, caso o
  utilizador prefira converter manualmente e depois importar como CSV
  (embora o upload direto de CSV não faça parte deste âmbito).

## 7. Testes / Verificação

Não existem testes automatizados no projeto; verificação é manual/visual:

1. **Regressão Excel:** upload de um `.xlsx` existente produz a mesma
   tabela pivot que antes (pipeline inalterado).
2. **PDF → DataFrame:** upload de um `Reservas.pdf` de exemplo produz um
   `df` com as colunas exatas
   `['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']`.
3. **PDF → pivot:** a tabela final do PDF é comparável à do Excel
   equivalente para o mesmo período.
4. **PDF inválido / vazio:** mostra `st.error` e para graciosamente.
5. **CLI inalterado:** correr `python parse_reservas.py Reservas.pdf`
   continua a gerar `reservas.csv` e `reservas_full.csv`, agora com o
   cabeçalho `"Dt. Criação"` corrigido.

## 8. Fora de âmbito

- Upload direto de CSV (não pedido).
- Refactor do `main.py` além da adição do ramo PDF.
- Alteração das colunas exportadas ou da lógica de pivot/totais.
- Testes automatizados (fora do pedido; projeto sem framework de testes).
- Cache do parsing PDF (Streamlit `@st.cache_data`).
- Suporte a PDFs com layout diferente do "LISTAGEM DE RESERVAS" atual.