# PetVida — Camada de acesso a dados (Python + SQL Server com pyodbc)

Desafio técnico: conexão segura entre Python e o banco **PetVida** (clínica
veterinária) e CRUD de tutor, pet, consulta e procedimentos.

## Arquivos

| Arquivo | Função |
|---|---|
| `db.py` | Etapa 1 — connection string, `conectar()`, `testar_conexao()` e o gerenciador de transação `transacao()` |
| `repositorio.py` | Etapas 2, 3 e 4 + bônus `historico_do_pet()` |
| `testar_repositorio.py` | Teste de fumaça: confere cada regra da atividade contra o banco real |
| `01_estrutura_petvida.sql` | Script do banco entregue pelo professor (não foi alterado) |

## Requisitos

- Python 3.10+
- SQL Server 2019/2022 (autenticação mista habilitada)
- **ODBC Driver 18 for SQL Server** instalado no sistema
- Biblioteca `pyodbc`

## Como configurar

1. **Criar o banco.** Execute `01_estrutura_petvida.sql` no Azure Data Studio (ou SSMS/sqlcmd)
   conectado como administrador. O script recria o banco `PetVida` do zero; a consulta final
   deve listar 5 consultas.

2. **Instalar o driver ODBC (Ubuntu 22.04):**
   ```bash
   curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
   curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
   sudo apt-get update
   sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev
   ```
   No Windows, instale o "ODBC Driver 18 for SQL Server" pelo instalador da Microsoft.

3. **Criar o ambiente virtual e instalar o pyodbc:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install pyodbc
   ```

4. **Definir as variáveis de ambiente** (nenhuma credencial fica no código):

   | Variável | Exemplo | Observação |
   |---|---|---|
   | `PETVIDA_SERVER` | `localhost,1433` | servidor e porta |
   | `PETVIDA_DB` | `PetVida` | nome do banco |
   | `PETVIDA_USER` | `sa` | se **omitida**, usa autenticação Windows (`Trusted_Connection=yes`) |
   | `PETVIDA_PASSWORD` | `********` | senha do usuário SQL |

   ```bash
   export PETVIDA_SERVER='localhost,1433'
   export PETVIDA_DB='PetVida'
   export PETVIDA_USER='sa'
   export PETVIDA_PASSWORD='sua_senha'
   ```
   (PowerShell: `$env:PETVIDA_SERVER = "localhost,1433"`, e assim por diante.)

## Como rodar

```bash
python -c "import db; print(db.testar_conexao())"   # servidor, banco e versão
python testar_repositorio.py                         # verifica todas as regras
```

Uso no código:

```python
import repositorio as repo
from datetime import datetime

id_tutor = repo.criar_tutor("Maria Silva", "11122233344", "maria@email.com")
id_pet = repo.criar_pet(id_tutor, "Bidu", "Cão", peso_kg=8.5)
id_consulta = repo.agendar_consulta(id_pet, 1, datetime(2026, 11, 3, 9, 0),
                                    "Vacinação", [(2, 1), (3, 1)])
print(repo.total_da_consulta(id_consulta))
```

## Decisões técnicas

- **Sem SQL Injection:** todo dado externo entra por parâmetro `?`. A única consulta com nomes
  dinâmicos é `atualizar_tutor`, e os nomes de coluna vêm de uma lista branca
  (`nome`, `email`, `telefone`). O filtro de `listar_tutores` usa `LIKE ?` com `ESCAPE`.
- **Sem conexão global:** `db.transacao()` abre a conexão, faz `commit` se tudo deu certo,
  `rollback` se algo falhou e sempre fecha no `finally`. `autocommit=False`.
- **Atomicidade:** `agendar_consulta` grava a consulta e todos os itens na mesma transação;
  se um item falhar, nada é gravado.
- **Preço congelado:** o item é inserido com `INSERT ... SELECT preco_base`, ou seja, o
  `valor_cobrado` recebe o preço base vigente naquele momento.
- **Chaves geradas:** `OUTPUT INSERTED.id_...` devolve o id sem uma segunda consulta.
- **Tradução de erros:** `repositorio.py` converte `pyodbc.IntegrityError`,
  `OperationalError` etc. em exceções de negócio, identificando a constraint pelo nome
  (funciona com o SQL Server em qualquer idioma):

  | Exceção | Quando |
  |---|---|
  | `RegistroDuplicado` | CPF/CRMV/descrição repetidos, procedimento repetido na consulta |
  | `RegistroNaoEncontrado` | id inexistente ou referência (FK) a registro que não existe |
  | `OperacaoBloqueada` | excluir tutor com pets, pet com consultas; alterar consulta cancelada |
  | `DadoInvalido` | CPF fora do padrão, espécie/status inválido, peso ≤ 0, quantidade ≤ 0 |
  | `ErroConexao` | servidor fora do ar, senha errada |
  | `ErroBanco` | qualquer outro erro do banco |

- A estrutura do banco **não foi alterada**: todas as regras (CPF, espécie, status, exclusões
  bloqueadas, cascata) são do próprio script e o Python apenas as respeita e traduz.

## Observações

- `buscar_tutor()` e `buscar_pet_com_tutor()` devolvem `None` quando não encontram.
- `historico_do_pet()` filtra a view `vw_resumo_consulta` por JOIN com `dbo.consulta`,
  porque a view não expõe `id_pet`.
- `adicionar_procedimento()` e `remover_procedimento()` recusam consultas `CANCELADA`.
## Verificação

Como não foi fornecido um verificador externo, a verificação foi feita com o script
`testar_repositorio.py`, que executa as funções do repositório contra o banco PetVida e confere
cada regra do enunciado (parametrização contra SQL Injection, chaves geradas por
OUTPUT INSERTED, relacionamentos 1:N e N:M, rollback do `agendar_consulta`, tradução de
erros do banco e bloqueio de exclusões).

Resultado da execução: **39/39 verificações aprovadas** (ver `print_verificador.png`).

Para reproduzir: `python testar_repositorio.py`
