EMUSA BRASIL – CONTROLE E MONITORAMENTO DE ENERGIA (em desenvolvimento)

Dashboard em Dash/Plotly para monitoramento de energia com leitura Modbus (KRON) ou simulador, persistência em PostgreSQL, exportação CSV/PDF e base para análises com IA e integração Power BI.
Branding no app e relatórios: EMUSA BRASIL – By Leo Moreno.

🚧 Status: Em desenvolvimento e testes. Este repositório está evoluindo rapidamente.

✨ Recursos atuais

Leitura em tempo real:

Simulador (para desenvolvimento em casa) ou KRON real (na empresa)

Detecção automática da porta COM/CH30 disponível (testa portas e canais, valida conexão e inicia o dashboard já conectado).

KPIs: Tensão LL média, Potência ativa (kW), FP, Frequência (Hz), Energia kWh A

Gráficos:

LL R/S/T com onda senoidal animada (amplitude via RMS real)

Energia kWh A em tempo real (histórico curto)

Exportações:

CSV (últimas 24h) – pronto para Power BI

PDF (últimas 24h) – gerado com ReportLab e baixado via dcc.Download (Base64)

Relatórios automáticos (IA): resumo compartilhado a cada 6 horas diretamente no dashboard (nenhum relatório automático antes desse intervalo).

Persistência:

PostgreSQL com schema inicial automático

UI:

Paleta dark (azul/preto/branco), layout mais limpo e responsivo

Aba exclusiva “IA & Diagnóstico” com registros monitorados, gráficos de comportamento (kW/Hz/FP) e últimos relatórios automáticos.

🧭 Roadmap (próximas entregas)

🔜 Segundo KRON (mesmo modelo), somando potência ativa total

🔜 Alertas automáticos (WhatsApp/E-mail) com anomalias da IA

E-mail diário (24h)

E-mail quinzenal (análise de demanda: ponta/fora-ponta, tendências)

🔜 Botão Power BI na UI e melhorias no botão de PDF

🔜 Relatório PDF mais rico (comentários de IA “para gerente”)

🔜 Suporte Modbus TCP (ex.: Siemens PAC 3200)

🔜 Registro ampliado (correntes L1/L2/L3, L-L, kWh acumulado B, etc.)

📁 Estrutura do projeto
EMUSA_DASHBOARD/
  app.py
  db.py
  report_24h.py
  modbus_reader.py            # leitor real (empresa)
  modbus_reader_sim.py        # simulador (casa/dev)
  registers_kron03_real.json  # mapa de registradores (KRON)
  requirements.txt
  .env.example
  README.md
  RELATORIOS/                 # PDFs gerados

🧩 Pré-requisitos

Windows 10/11

Python 3.12+ (py --version)

pip instalado

PostgreSQL 16 (serviço em execução)

Git (opcional, para clonar o repo)

Dependências Python:

py -m pip install -r requirements.txt
py -m pip install reportlab python-dotenv

🚀 Setup rápido (Windows)
1) Obter o código

Via Git:

git clone https://github.com/leomorenonodered/emusadashbord.git
cd emusadashbord/EMUSA_DASHBOARD


Ou baixe o ZIP do GitHub e extraia em:

C:\Users\<SeuUsuario>\Desktop\EMUSA_DASHBOARD

2) Instalar dependências
py -m pip install -r requirements.txt
py -m pip install reportlab python-dotenv

3) Configurar o banco (.env)

Crie .env na raiz (ou copie de .env.example) com:

PG_HOST=localhost
PG_PORT=5432
PG_DB=emusa_energy
PG_USER=emusa
PG_PASSWORD=74087432

Criar usuário e banco (se ainda não existir)

Abra o psql (ajuste a versão se necessário):

& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -U postgres postgres


No prompt postgres=#, cole:

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'emusa') THEN
      CREATE ROLE emusa LOGIN PASSWORD '74087432';
   END IF;
END$$;

ALTER ROLE emusa CREATEDB;

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'emusa_energy') THEN
      CREATE DATABASE emusa_energy OWNER emusa;
   END IF;
END$$;

\c emusa_energy
ALTER SCHEMA public OWNER TO emusa;
GRANT ALL ON SCHEMA public TO emusa;
\q

4) Escolher a fonte (Simulador x KRON real)

Desenvolvimento (sem KRON, em casa):

set USE_SIM=1
py app.py


Produção (com KRON, na empresa):

set USE_SIM=0
py app.py


Garanta que modbus_reader.py esteja com as configurações corretas (porta COM, baud 9600, 8N2, slave 1, endian DCBA) e que o registers_kron03_real.json contenha os registradores validados.

💡 Dica: crie um run_dashboard.bat com:

@echo off
set USE_SIM=1
py app.py

🖥️ Uso

Acesse o dashboard em: http://127.0.0.1:8050

KPIs em tempo real e gráficos:

LL (R/S/T): ondas senoidais com defasagem de 120°, amplitude a partir do RMS lido

Energia kWh A: histórico curto (tempo real)

Botões:

Exportar (CSV – Power BI): exporta últimas 24h

PDF 24h (com IA): gera relatório em RELATORIOS/ e baixa automaticamente

🧾 Sobre o PDF (24h)

Geração em report_24h.py com ReportLab.

Conteúdos:

Resumo executivo (IA enxuta, foco no usuário final)

KPIs e estatísticas: médias, máximos, mínimos

Anomalias simples (ex.: variação de tensão, picos de corrente/potência)

Janelas de maior consumo

Download no Dash requer Base64:

import base64
with open(fpath, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")
return {"content": b64, "filename": fname, "type": "application/pdf", "base64": True}

📊 Power BI

Conector PostgreSQL:

Servidor: localhost

Banco: emusa_energy

Porta: 5432

Usuário: emusa

Senha: 74087432

Importe a tabela de leituras e construa visuais.
(Planejado: gravar comentários/insights da IA em tabela própria para ingestão direta pelo Power BI.)

🔌 Leitor Modbus (KRON)

modbus_reader.py deve expor:

connect() — configura porta/parâmetros

read_all() — retorna dict com chaves usadas no app (ex.: tensao_ll_l1, corrente_l1, potencia_kw_inst, energia_kwh_a, etc.)

Mapa de registradores: registers_kron03_real.json

Campos típicos: fn (03/04), addr, kind (U32, U64, F32), endian (DCBA)

Se algum L-L faltar, o app calcula média pelas demais para manter o KPI preenchido.

🛟 Solução de problemas

app.run_server obsoleto
Use app.run(...). O projeto já está atualizado.

Erro no download do PDF (bytes não serializável)
Retorne Base64 no dcc.Download (veja o snippet acima).

database does not exist / password authentication failed
Crie o DB/usuário conforme a seção de setup e confira o .env.

git não reconhecido
Instale o Git e/ou reabra o terminal após a instalação.

Dica: se aparecer Tip: There are .env or .flaskenv files present.
Garanta py -m pip install python-dotenv.

🤝 Contribuição

Projeto em desenvolvimento e testes.
Issues e PRs são super bem-vindos.
Padrões: Python 3.12, Dash/Plotly (flake8 opcional).

📄 Licença

 Leo Moreno

Créditos
EMUSA BRASIL – Controle e Monitoramento de Energia
By Leo Moreno
