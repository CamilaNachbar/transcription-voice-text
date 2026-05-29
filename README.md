# Transcritor Inteligente de Reuniões (Desktop)

Aplicativo desktop (sem navegador) para capturar áudio de microfone + áudio do computador, transcrever automaticamente com pausa por silêncio, organizar sessões por data/hora e gerar resumo inteligente com Claude.

## Funcionalidades

- Captura de voz local sem browser.
- Duas entradas: **sua voz** (microfone) e **participantes** (Teams, Meet, Zoom, áudio do PC).
- Detecção de silêncio para segmentar fala automaticamente.
- Transcrição contínua com `faster-whisper` (**sempre local**).
- Refinamento da transcrição e resumo com IA via **Anthropic** (direto, gateway ou Flow) ou **Cursor SDK**.
- Interface desktop (CustomTkinter) com histórico de sessões por data/hora.
- Exportação em `.txt`:
  - `transcricao_raw.txt`
  - `transcricao_formatada.txt`
  - `resumo.txt`

## Requisitos

- Python 3.11+
- Windows ou macOS
- Para resumo/refino: uma das configurações de IA abaixo (opcional para usar só transcrição local)

---

## Instalação (todos os cenários)

Passo único, igual para qualquer modo de uso:

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Para transcrever **participantes** da reunião no Mac, configure o [BlackHole](#macos--configuração-do-blackhole) antes de usar o app.

Depois da instalação, escolha **um** cenário de IA na seção seguinte e edite o `.env` (ou variáveis de ambiente). Não é necessário configurar todos.

---

## Escolha o seu cenário

| Cenário | O que funciona | Rede para IA | Ideal para |
|--------|----------------|--------------|------------|
| [1 — Só transcrição local](#1--só-transcrição-local) | Whisper + arquivos `.txt` brutos | Não | Testar áudio, sem chaves |
| [2 — Anthropic direto](#2--anthropic-direto-api-oficial) | Transcrição + refino + resumo | `api.anthropic.com` | Conta Anthropic pessoal/empresa |
| [3 — CI&T Flow LiteLLM](#3--cit-flow-litellm) | Transcrição + refino + resumo | Proxy Flow | Colaboradores CI&T (JWT) |
| [4 — Gateway corporativo](#4--gateway-corporativo-litellm-ou-proxy-interno) | Transcrição + refino + resumo | Proxy interno | Proxy LiteLLM/Bedrock da empresa |
| [5 — Cursor SDK](#5--cursor-sdk) | Transcrição + refino + resumo | API Cursor | VPN bloqueia Anthropic, Cursor liberado |
| [6 — Automático com fallback](#6--automático-com-fallback) | Tenta provedores em ordem | Depende da ordem | Ambiente instável / VPN mista |

**Complementos** (somam a qualquer cenário que use rede):

- [Proxy HTTP (VPN)](#complemento-proxy-http-vpn)
- [Certificado SSL corporativo (NetSkope)](#complemento-certificado-ssl-netskope)

O que roda **sempre na máquina**, em todos os cenários: captura de áudio, detecção de silêncio e Whisper. Apenas formatação e resumo usam rede quando há provedor de IA configurado.

---

## Configuração por cenário

Edite o arquivo `.env` na raiz do projeto. Na interface, o rodapé **Provedor de IA** deve bater com o cenário (`Anthropic` para 2–4, `Cursor` para 5, `Automático` para 6).

### Variáveis comuns

| Variável | Função |
|----------|--------|
| `LLM_PROVIDER` | `anthropic`, `cursor` ou `auto` |
| `LLM_FALLBACK_ORDER` | Só no modo `auto` — ordem de tentativa (ex.: `cursor,anthropic`) |

---

### 1 — Só transcrição local

Sem chaves de API. Útil para validar microfone, loopback e Whisper antes de configurar IA.

**.env**

```env
# Deixe chaves vazias ou não defina LLM — o app grava transcricao_raw.txt
LLM_PROVIDER=anthropic
```

**Subir o app**

```bash
python run.py
```

**Resultado:** transcrição ao vivo e `transcricao_raw.txt` ao parar. Sem `transcricao_formatada.txt` refinada nem `resumo.txt` (mensagem de indisponível no resumo).

---

### 2 — Anthropic direto (API oficial)

Chave em [console.anthropic.com](https://console.anthropic.com). Requer acesso à internet até `api.anthropic.com` (sem proxy Flow).

**.env**

```env
LLM_PROVIDER=anthropic

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
# ANTHROPIC_BASE_URL=   # deixe vazio para API oficial
```

**Subir o app**

```bash
python run.py
```

Na UI: **Provedor de IA → Anthropic**.

---

### 3 — CI&T Flow LiteLLM

Recomendado para quem usa [CI&T Flow](https://flow.ciandt.com). O app fala com o proxy Flow via SDK Anthropic (`ANTHROPIC_BASE_URL` + JWT), no mesmo espírito do [guia Flow + agentes](https://ciandtflow.featurebase.app/pt-BR/help/articles/8421153-visao-geral-and-configuracao).

#### Passo A — Gerar JWT (uma vez)

1. Crie API Keys no Flow (`clientId`, `clientSecret`, `tenant` — **só aparecem na criação**).
2. Em [jwt.io](https://jwt.io) → **JWT Encoder**:
   - Header: `{"alg":"HS256","typ":"JWT"}`
   - Payload:

```json
{
  "clientId": "<seu-client-id>",
  "clientSecret": "<seu-client-secret>",
  "tenant": "<seu-tenant>"
}
```

3. Copie o token — **não compartilhe**.

#### Passo B — `.env` deste projeto

```env
LLM_PROVIDER=anthropic

FLOW_LITELLM_PROXY=https://flow.ciandt.com/flow-llm-proxy
FLOW_API_KEY=<seu-jwt>

ANTHROPIC_MODEL=bedrock/anthropic.claude-4-6-sonnet
```

Equivalentes aceitos: `ANTHROPIC_API_KEY` ou `ANTHROPIC_AUTH_TOKEN` no lugar de `FLOW_API_KEY`; se `ANTHROPIC_BASE_URL` estiver vazio, o app usa `FLOW_LITELLM_PROXY`.

**Bradesco (BSEG):** `FLOW_LITELLM_PROXY=https://flow-bseg.ciandt.com/flow-llm-proxy`

**Modelos (exemplos no Flow):** `bedrock/anthropic.claude-4-6-sonnet`, `bedrock/anthropic.claude-4-5-haiku` — lista completa no portal Flow.

#### Passo C — Validar antes de gravar reunião

```bash
python scripts/test-flow-llm.py
```

Saída esperada: `Sucesso — Flow LiteLLM está acessível para este app.`

#### Passo D — Subir o app

```bash
python run.py
```

Na UI: **Provedor de IA → Anthropic**.

**PowerShell (sem `.env`, sessão atual):**

```powershell
$env:FLOW_LITELLM_PROXY = "https://flow.ciandt.com/flow-llm-proxy"
$env:FLOW_API_KEY = "<seu-jwt>"
$env:ANTHROPIC_MODEL = "bedrock/anthropic.claude-4-6-sonnet"
python run.py
```

---

### 4 — Gateway corporativo (LiteLLM ou proxy interno)

Para empresas com proxy próprio (não Flow). Ajuste URL e modelo conforme o time de infra.

**.env**

```env
LLM_PROVIDER=anthropic

ANTHROPIC_API_KEY=<token-do-gateway>
ANTHROPIC_BASE_URL=https://llm-proxy.sua-empresa.internal
ANTHROPIC_MODEL=<id-do-modelo-no-proxy>
```

**Subir o app**

```bash
python run.py
```

Na UI: **Provedor de IA → Anthropic**.

---

### 5 — Cursor SDK

Usa o agente Cursor na máquina. Chave em [cursor.com/settings](https://cursor.com/settings) (API / Agents). Não usa `ANTHROPIC_*`.

**.env**

```env
LLM_PROVIDER=cursor

CURSOR_API_KEY=<sua-chave-cursor>
CURSOR_MODEL=composer-2.5
```

Dependência (se ainda não instalou): `pip install cursor-sdk`

**Subir o app**

```bash
python run.py
```

Na UI: **Provedor de IA → Cursor**.

---

### 6 — Automático com fallback

Tenta provedores em ordem até um responder. Útil quando às vezes só Cursor ou só Anthropic/Flow funciona na VPN.

**.env — priorizar Cursor**

```env
LLM_PROVIDER=auto
LLM_FALLBACK_ORDER=cursor,anthropic

CURSOR_API_KEY=...
ANTHROPIC_API_KEY=...          # ou FLOW_API_KEY + FLOW_LITELLM_PROXY
FLOW_LITELLM_PROXY=...         # opcional, cenário Flow
ANTHROPIC_MODEL=bedrock/anthropic.claude-4-6-sonnet
```

**.env — priorizar Anthropic/Flow**

```env
LLM_PROVIDER=auto
LLM_FALLBACK_ORDER=anthropic,cursor

FLOW_API_KEY=...
FLOW_LITELLM_PROXY=https://flow.ciandt.com/flow-llm-proxy
ANTHROPIC_MODEL=bedrock/anthropic.claude-4-6-sonnet
CURSOR_API_KEY=...
```

**Subir o app**

```bash
python run.py
```

Na UI: **Provedor de IA → Automático**. O título da janela indica qual provedor está ativo (`anthropic`, `cursor` ou `nenhum`).

---

## Complementos de rede

### Complemento: Proxy HTTP (VPN)

Adicione ao `.env` de qualquer cenário que chame APIs externas (2–6):

```env
HTTP_PROXY=http://proxy.empresa:8080
HTTPS_PROXY=http://proxy.empresa:8080
NO_PROXY=localhost,127.0.0.1
```

### Complemento: Certificado SSL (NetSkope)

Se `python scripts/test-flow-llm.py` ou o app falhar com `CERTIFICATE_VERIFY_FAILED`, peça o `.pem` ao IT e configure:

```env
SSL_CERT_FILE=C:\caminho\para\certificado-empresa.pem
REQUESTS_CA_BUNDLE=C:\caminho\para\certificado-empresa.pem
```

No macOS com NetSkope, o guia Flow costuma apontar para `nscacert.pem` em Application Support — use o caminho que o suporte informar.

---

## Executar (resumo)

```bash
# Ativar venv (Windows)
.venv\Scripts\activate

# Rodar
python run.py
```

| Cenário | Comando extra recomendado |
|---------|---------------------------|
| Flow (3) | `python scripts/test-flow-llm.py` antes da primeira reunião |
| Demais com IA | Abrir o app e conferir o provedor no título da janela |

---

## Como usar

1. Clique em **Iniciar Reunião**.
2. O app captura áudio e transcreve em tempo real.
3. Pausas de fala são detectadas automaticamente.
4. Clique em **Parar e Gerar Arquivos** para salvar transcrição e resumo.
5. Use a lista à esquerda para abrir sessões antigas por data/hora.
6. **Apagar selecionada** ou **Apagar todas** remove os arquivos da pasta `data/sessions/` (com confirmação).
7. **Testar conexão IA** (rodapé) verifica Anthropic/Flow, Cursor e o provedor selecionado na interface.
6. No rodapé: **Provedor de IA** (Automático / Anthropic / Cursor) e tema **Claro / Escuro / Sistema**.
7. Preferências ficam em `data/user_settings.json`.

### Interface

- Botões **Iniciar** e **Parar** com indicador de status.
- Painel central: transcrição ao vivo e resultados.
- Barra lateral: histórico por data/hora.

---

## Referência rápida de variáveis

| Variável | Cenários |
|----------|----------|
| `FLOW_LITELLM_PROXY`, `FLOW_API_KEY` | 3 (Flow) |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` | 2, 4; também 3 (alternativas) |
| `ANTHROPIC_AUTH_TOKEN` | 3 (mesmo JWT que `FLOW_API_KEY`) |
| `CURSOR_API_KEY`, `CURSOR_MODEL` | 5, 6 |
| `LLM_PROVIDER`, `LLM_FALLBACK_ORDER` | 6 (e controle geral) |
| `HTTP_PROXY`, `HTTPS_PROXY` | Complemento VPN |
| `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` | Complemento NetSkope |

---

## Reuniões online (Teams, Meet, Zoom, navegador)

O app usa **duas entradas ao mesmo tempo**:

| Entrada no app | O que captura | Rótulo na transcrição |
|----------------|---------------|------------------------|
| **Microfone** | Sua voz | `Você` |
| **Participantes (Teams, Meet…)** | Áudio que sai no PC (outros na call) | `Participante A`, `B`, `C`… (por timbre de voz) |

Funciona para **Microsoft Teams**, **Google Meet**, **Zoom**, chamadas no navegador e qualquer app que reproduza som na saída do sistema.

- **Windows:** loopback WASAPI — veja [Configuração recomendada](#configuração-recomendada) abaixo.
- **macOS:** configure o [BlackHole](#macos--configuração-do-blackhole) antes de gravar participantes.

### Configuração recomendada (Windows)

1. **Use fone de ouvido** — evita que o microfone grave de novo o áudio dos participantes (eco/duplicata).
2. **Microsoft Teams** → **Configurações** → **Dispositivos** → defina **Alto-falante** igual ao item **Participantes** no app.
3. **Windows** → **Configurações** → **Som** → **Saída** = mesmo dispositivo (★ no app = saída padrão do Windows).
4. No app, deixe ligado **Capturar voz dos participantes** e clique **Iniciar reunião**.

No **Mac**, siga o guia [macOS — configuração do BlackHole](#macos--configuração-do-blackhole) em vez desta lista.

### Google Meet no Chrome

O botão **Chrome + gravar** abre o Chrome na URL configurada (padrão: Google Meet) e inicia a transcrição **neste app**. Ele **não** aciona a gravação interna do navegador — a captura continua sendo microfone + áudio do PC, como acima.

Na aba **Áudio**, edite **URL no Chrome** (ex.: `https://teams.microsoft.com`, `https://zoom.us/j/...`) ou use no `.env`:

```env
CHROME_MEETING_URL=https://meet.google.com/new
```

Headsets com dois perfis (ex.: «Chat» vs «Game»): o Teams pode usar um e o Windows outro — alinhe os três (Teams, Windows e app).

### Ajuste fino (opcional, `.env`)

Latência da transcrição ao vivo (valores padrão já otimizados):

```env
SILENCE_TIMEOUT_SECONDS=0.75    # pausa para fechar um trecho (microfone)
SYSTEM_SILENCE_TIMEOUT_SECONDS=1.15
MAX_SEGMENT_SECONDS=12          # envia trecho mesmo sem pausa longa
PREFIX_PADDING_SECONDS=0.45     # não perde o início da fala
SYSTEM_SILENCE_THRESHOLD=0.006
```

### Listar dispositivos

```bash
python scripts/list-audio-devices.py
```

Se os participantes não aparecem na transcrição, quase sempre é saída de som diferente entre Teams, Windows e o app.

### Assistente de IA (botões)

Durante a gravação, use na barra superior:

| Botão | O que a IA faz |
|-------|----------------|
| **Resumir (IA)** | Só o resumo da reunião até o momento |
| **Responder (IA)** | Resumo + sugestão do que você pode falar (usa o último resumo gerado, se existir) |

O resultado aparece na transcrição ao vivo e em `assistente_*.txt`.

### Pedidos personalizados (listas, pautas, e-mail…)

Na aba **Inteligência artificial**, seção **Pedidos à IA sobre a transcrição**:

1. Durante a gravação, escolha um **modelo de pedido** (lista de tarefas, pauta da próxima reunião, e-mail de follow-up, etc.) ou escreva seu pedido em português.
2. Edite o texto se quiser ser mais específico.
3. Clique em **Enviar pedido à IA**.

A IA usa só o que já foi transcrito (e o último resumo gerado, se existir). Se faltar informação, ela sugere o que perguntar na reunião em vez de inventar.

```env
# Nome usado nas sugestões de resposta da IA (opcional)
ASSISTANT_USER_NAME=Camila
```

### Perfis de voz (vários participantes)

Com `speechbrain` instalado (`pip install -r requirements.txt`), o app tenta **separar falantes** no áudio da reunião:

- **Você** — sempre o microfone local.
- **Participante A, B, C…** — vozes distintas no áudio remoto; o perfil é mantido durante a sessão.

Requisitos para boa separação:

- Fone de ouvido (áudio remoto limpo no loopback).
- Vozes realmente diferentes (não identifica nome real, só timbre).
- Trechos de reunião com pelo menos ~2 s de fala por pessoa.

Desative no `.env` se quiser só «Participantes (reunião)» genérico:

```env
DIARIZATION_ENABLED=false
```

Ajuste sensibilidade: `SPEAKER_MATCH_THRESHOLD=0.72` (menor = mais perfis; maior = agrupa mais).

---

## macOS — configuração do BlackHole

No Mac **não há** loopback nativo como no Windows (WASAPI). Para transcrever **outras pessoas na call**, o áudio da reunião precisa passar pelo **BlackHole** (ou dispositivo virtual equivalente). O app lê o BlackHole na lista **Participantes**.

```
Reunião (Meet/Teams/Zoom)
        ↓
Saída do Mac = «Dispositivo com saída múltipla»
        ├─→ Fones/alto-falante (você ouve)
        └─→ BlackHole 2ch (o app grava daqui)
```

### 1. Instalar o BlackHole

1. Baixe e instale o **[BlackHole 2ch](https://existential.audio/blackhole/)** (versão gratuita; use **2ch** para reuniões).
2. Se o instalador pedir, **reinicie o Mac**.
3. Em **Ajustes do Sistema → Privacidade e segurança → Microfone**, permita:
   - o **Terminal** (se roda `python run.py` pelo terminal), ou
   - o interpretador Python / IDE que você usa.

Sem permissão de microfone, o app não consegue abrir o BlackHole como entrada de áudio.

### 2. Criar saída múltipla (Áudio MIDI)

Você precisa **ouvir** a reunião e **enviar cópia** do som para o BlackHole.

1. Abra **Configuração de Áudio MIDI**  
   - Spotlight: digite `Audio MIDI Setup` ou `Configuração de Áudio MIDI`.
2. No canto inferior esquerdo, clique em **+** → **Criar dispositivo com saída múltipla** (Create Multi-Output Device).
3. Marque **as duas** opções (ordem sugerida):
   - **BlackHole 2ch**
   - Seus **fones** ou **alto-falante** (o que você usa para ouvir)
4. Opcional: clique com o botão direito no dispositivo criado → **Usar este dispositivo para saída de som** (Use This Device For Sound Output).
5. Renomeie para algo claro, ex.: `Reunião + BlackHole`.

**Importante:** marque só **BlackHole 2ch**, não «BlackHole 16ch», a menos que você saiba que precisa de mais canais.

### 3. Definir saída do sistema

1. **Ajustes do Sistema → Som → Saída** → escolha o dispositivo **Reunião + BlackHole** (sua saída múltipla).
2. Ajuste o volume do sistema; o volume dos fones costuma seguir a saída múltipla.

Todo áudio do Mac (navegador, Teams, Zoom, Meet) deve passar por essa saída enquanto você grava.

### 4. Configurar a reunião (Meet / Teams / Zoom)

Alinhe o app da reunião com a **mesma** saída:

| App | Onde configurar |
|-----|-----------------|
| **Google Meet** (Chrome) | Três pontos → **Configurações** → **Áudio** → **Alto-falante** = saída múltipla ou «Padrão do sistema» |
| **Microsoft Teams** | **Configurações** → **Dispositivos** → **Alto-falante** = mesmo dispositivo |
| **Zoom** | **Configurações de áudio** → **Alto-falante** = mesmo dispositivo |

Use **fone de ouvido** na saída múltipla para reduzir eco no seu microfone.

### 5. Configurar este app

1. Abra o transcritor: `python run.py`
2. Aba **Áudio**:
   - **Microfone** → seu microfone real
   - Ative **Capturar voz dos participantes (Teams, Meet, Zoom…)**
   - **Participantes na call** → **BlackHole 2ch**
3. Se **BlackHole 2ch** não aparecer → **Atualizar dispositivos** (ou reinicie o app após instalar o BlackHole).
4. Botão **Ajuda áudio (Mac)** — mesmo conteúdo resumido na interface.
5. **Iniciar reunião** ou **Chrome + gravar** (abre o Meet no Chrome e já inicia a transcrição).

Confirme os dispositivos no terminal:

```bash
python scripts/list-audio-devices.py
```

Na seção **Participantes**, deve listar algo como `BlackHole 2ch`.

### 6. Teste rápido antes da call

1. Com a saída múltipla ativa, abra um vídeo no YouTube ou música no Spotify.
2. Inicie **Iniciar reunião** no app (pode parar em seguida).
3. Se a transcrição mostrar falas de **Participante A** (ou texto do áudio remoto), o roteamento está certo.
4. Se só aparecer **Você**, o som ainda não está chegando ao BlackHole — revise os passos 2 e 3.

### Problemas comuns (BlackHole)

| Sintoma | O que verificar |
|---------|------------------|
| BlackHole não aparece no app | Reinicie o Mac; reinstale o driver; **Atualizar dispositivos**; permissão de **Microfone** |
| Só transcreve «Você» | Saída do Mac não é a saída múltipla; Meet/Teams usa outro alto-falante |
| Áudio baixo ou mudo nos fones | Na saída múltipla, marque os fones **e** o BlackHole; aumente volume do sistema |
| Eco / duplicata na transcrição | Use fone; microfone longe do alto-falante |
| BlackHole instalado mas «não funciona» | Criou **saída múltipla**? Sem ela, o som vai só aos fones e não entra no BlackHole |

### Alternativas ao BlackHole

| Opção | Quando usar |
|-------|-------------|
| **[Loopback](https://rogueamoeba.com/loopback/)** (pago) | BlackHole instável ou roteamento complexo no seu Mac |
| **Só microfone** | Desative «Capturar participantes» — transcreve apenas sua voz |
| **Windows** | Loopback WASAPI nativo, sem BlackHole (veja [Configuração recomendada](#configuração-recomendada)) |

---

## Observações importantes

- **Windows:** loopback WASAPI na lista «Participantes». **macOS:** BlackHole/Loopback como entrada virtual.
- Sem provedor de IA, só o cenário **1** pleno; cenários 2–6 precisam das chaves corretas.
- O título da janela mostra o provedor ativo e o detalhe no rodapé (`Anthropic: ok`, `Cursor: —`, etc.).
