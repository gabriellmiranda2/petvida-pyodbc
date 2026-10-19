"""Camada de acesso a dados da clínica PetVida (pyodbc + SQL Server).

Regras seguidas em todas as funções:
  * todo valor vindo de fora entra no SQL por parâmetro (?), nunca por f-string;
  * nomes de colunas dinâmicos só vêm de listas brancas definidas aqui;
  * cada função abre e fecha sua própria conexão via db.transacao()
    (commit se tudo deu certo, rollback se algo falhou);
  * erros do banco são traduzidos para exceções de negócio (ErroNegocio).
"""
import functools
import re

import pyodbc

from db import transacao


# ----------------------------------------------------------------------
# Exceções de negócio
# ----------------------------------------------------------------------
class ErroNegocio(Exception):
    """Base de todos os erros que a aplicação sabe explicar ao usuário."""


class RegistroDuplicado(ErroNegocio):
    """Valor único já existe (CPF, CRMV, item repetido na consulta...)."""


class RegistroNaoEncontrado(ErroNegocio):
    """O registro procurado (ou referenciado) não existe."""


class OperacaoBloqueada(ErroNegocio):
    """A regra de negócio impede a operação (ex.: excluir tutor com pets)."""


class DadoInvalido(ErroNegocio):
    """Valor recusado por uma regra de validação (CHECK, tamanho, tipo)."""


class ErroConexao(ErroNegocio):
    """Não foi possível falar com o banco (servidor fora, senha errada...)."""


class ErroBanco(ErroNegocio):
    """Erro inesperado do banco, sem tradução específica."""


# ----------------------------------------------------------------------
# Tradução de erros do SQL Server
#   O nome da constraint aparece na mensagem em qualquer idioma do servidor,
#   por isso é ele (e não o texto da mensagem) que identifica o problema.
# ----------------------------------------------------------------------
_REGRAS_CONSTRAINT = {
    "uq_tutor_cpf": (RegistroDuplicado, "Já existe um tutor cadastrado com esse CPF."),
    "ck_tutor_cpf": (DadoInvalido, "CPF inválido: informe exatamente 11 dígitos numéricos."),
    "uq_vet_crmv": (RegistroDuplicado, "Já existe um veterinário com esse CRMV."),
    "uq_proc_desc": (RegistroDuplicado, "Já existe um procedimento com essa descrição."),
    "ck_pet_especie": (DadoInvalido, "Espécie inválida. Use: Cão, Gato, Ave, Roedor, Réptil ou Outro."),
    "ck_pet_peso": (DadoInvalido, "O peso deve ser maior que zero."),
    "ck_proc_preco": (DadoInvalido, "O preço do procedimento não pode ser negativo."),
    "ck_consulta_status": (DadoInvalido, "Status inválido. Use AGENDADA, REALIZADA ou CANCELADA."),
    "ck_cp_qtd": (DadoInvalido, "A quantidade deve ser maior que zero."),
    "ck_cp_valor": (DadoInvalido, "O valor cobrado não pode ser negativo."),
    "pk_consulta_procedimento": (RegistroDuplicado, "Esse procedimento já está na consulta."),
}

# FK: (mensagem se o registro referenciado não existe, mensagem se a exclusão é bloqueada)
_REGRAS_FK = {
    "fk_pet_tutor": ("O tutor informado não existe.",
                     "Não é possível excluir o tutor: ele ainda possui pets."),
    "fk_consulta_pet": ("O pet informado não existe.",
                        "Não é possível excluir o pet: ele possui consultas."),
    "fk_consulta_vet": ("O veterinário informado não existe.",
                        "Não é possível excluir o veterinário: ele possui consultas."),
    "fk_cp_consulta": ("A consulta informada não existe.",
                       "Não é possível excluir a consulta: ela possui itens."),
    "fk_cp_procedimento": ("O procedimento informado não existe.",
                           "Não é possível excluir o procedimento: ele já foi usado em consultas."),
}


def _traduzir(erro: pyodbc.Error) -> ErroNegocio:
    """Converte um erro do pyodbc em uma exceção de negócio."""
    if isinstance(erro, (pyodbc.OperationalError, pyodbc.InterfaceError)):
        return ErroConexao(
            "Não foi possível conectar ao banco de dados. "
            "Verifique servidor, usuário, senha e se o SQL Server está ativo."
        )
    texto = " ".join(str(a) for a in erro.args).lower()
    for nome, (classe, mensagem) in _REGRAS_CONSTRAINT.items():
        if nome in texto:
            return classe(mensagem)
    for nome, (inexistente, bloqueada) in _REGRAS_FK.items():
        if nome in texto:
            if re.search(r"\bdelete\b", texto):
                return OperacaoBloqueada(bloqueada)
            return RegistroNaoEncontrado(inexistente)
    if isinstance(erro, pyodbc.IntegrityError):
        return DadoInvalido("O banco recusou a operação por violar uma regra de integridade.")
    if isinstance(erro, pyodbc.DataError):
        return DadoInvalido("Valor inválido ou grande demais para o campo.")
    return ErroBanco("Erro inesperado no banco de dados.")


def _tratar_erros(funcao):
    """Decorador: qualquer pyodbc.Error vira uma ErroNegocio compreensível."""
    @functools.wraps(funcao)
    def envoltorio(*args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except ErroNegocio:
            raise
        except pyodbc.Error as e:
            raise _traduzir(e) from e
    return envoltorio


def _escapar_like(texto: str) -> str:
    """Escapa %, _ e [ para o texto ser buscado literalmente no LIKE."""
    for ch in ("\\", "%", "_", "["):
        texto = texto.replace(ch, "\\" + ch)
    return texto


# ======================================================================
# ETAPA 2 — CRUD de tutor
# ======================================================================
CAMPOS_TUTOR_EDITAVEIS = {"nome", "email", "telefone"}  # lista branca


@_tratar_erros
def criar_tutor(nome, cpf, email=None, telefone=None) -> int:
    """Cadastra um tutor e devolve o id_tutor gerado (IDENTITY)."""
    if not isinstance(cpf, str):
        raise DadoInvalido("O CPF deve ser informado como texto (para não perder zeros à esquerda).")
    with transacao() as cur:
        cur.execute(
            "INSERT INTO dbo.tutor (nome, cpf, email, telefone) "
            "OUTPUT INSERTED.id_tutor VALUES (?, ?, ?, ?)",
            nome, cpf, email, telefone,
        )
        return cur.fetchone()[0]


@_tratar_erros
def buscar_tutor(id_tutor):
    """Devolve a linha do tutor, ou None se não existir."""
    with transacao() as cur:
        cur.execute("SELECT * FROM dbo.tutor WHERE id_tutor = ?", id_tutor)
        return cur.fetchone()


@_tratar_erros
def listar_tutores(filtro_nome=""):
    """Lista tutores cujo nome contém o filtro (LIKE parametrizado)."""
    padrao = f"%{_escapar_like(filtro_nome or '')}%"
    with transacao() as cur:
        cur.execute(
            r"SELECT * FROM dbo.tutor WHERE nome LIKE ? ESCAPE '\' ORDER BY nome",
            padrao,
        )
        return cur.fetchall()


@_tratar_erros
def atualizar_tutor(id_tutor, **campos):
    """Atualiza nome, email e/ou telefone. Qualquer outro campo é recusado."""
    if not campos:
        raise DadoInvalido("Informe ao menos um campo para atualizar.")
    invalidos = set(campos) - CAMPOS_TUTOR_EDITAVEIS
    if invalidos:
        raise DadoInvalido(
            f"Campos não permitidos: {', '.join(sorted(invalidos))}. "
            f"Permitidos: {', '.join(sorted(CAMPOS_TUTOR_EDITAVEIS))}."
        )
    # Os nomes das colunas vêm da lista branca acima; os valores vão por "?".
    atribuicoes = ", ".join(f"{coluna} = ?" for coluna in campos)
    with transacao() as cur:
        cur.execute(
            f"UPDATE dbo.tutor SET {atribuicoes} WHERE id_tutor = ?",
            *campos.values(), id_tutor,
        )
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Tutor não encontrado.")


@_tratar_erros
def excluir_tutor(id_tutor):
    """Exclui o tutor. O banco bloqueia se ele tiver pets."""
    with transacao() as cur:
        cur.execute("DELETE FROM dbo.tutor WHERE id_tutor = ?", id_tutor)
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Tutor não encontrado.")


# ======================================================================
# ETAPA 3 — Relacionamento 1:N tutor -> pet
# ======================================================================
@_tratar_erros
def criar_pet(id_tutor, nome, especie, raca=None, data_nascimento=None, peso_kg=None) -> int:
    """Cadastra um pet para um tutor e devolve o id_pet gerado."""
    with transacao() as cur:
        cur.execute(
            "INSERT INTO dbo.pet (id_tutor, nome, especie, raca, data_nascimento, peso_kg) "
            "OUTPUT INSERTED.id_pet VALUES (?, ?, ?, ?, ?, ?)",
            id_tutor, nome, especie, raca, data_nascimento, peso_kg,
        )
        return cur.fetchone()[0]


@_tratar_erros
def atualizar_peso_pet(id_pet, peso_kg):
    with transacao() as cur:
        cur.execute("UPDATE dbo.pet SET peso_kg = ? WHERE id_pet = ?", peso_kg, id_pet)
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Pet não encontrado.")


@_tratar_erros
def transferir_pet(id_pet, novo_id_tutor):
    """Passa o pet para outro tutor (a FK recusa tutor inexistente)."""
    with transacao() as cur:
        cur.execute(
            "UPDATE dbo.pet SET id_tutor = ? WHERE id_pet = ?",
            novo_id_tutor, id_pet,
        )
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Pet não encontrado.")


@_tratar_erros
def excluir_pet(id_pet):
    """Exclui o pet. O banco bloqueia se ele tiver consultas."""
    with transacao() as cur:
        cur.execute("DELETE FROM dbo.pet WHERE id_pet = ?", id_pet)
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Pet não encontrado.")


@_tratar_erros
def listar_pets_do_tutor(id_tutor):
    """Navegação lado 1 -> lado N: todos os pets de um tutor."""
    with transacao() as cur:
        cur.execute(
            "SELECT * FROM dbo.pet WHERE id_tutor = ? ORDER BY nome", id_tutor
        )
        return cur.fetchall()


@_tratar_erros
def buscar_pet_com_tutor(id_pet):
    """Navegação lado N -> lado 1 (JOIN): o pet junto com os dados do tutor."""
    with transacao() as cur:
        cur.execute(
            "SELECT p.id_pet, p.nome, p.especie, p.raca, p.data_nascimento, p.peso_kg, "
            "       t.id_tutor, t.nome AS nome_tutor, t.cpf, t.email, t.telefone "
            "FROM dbo.pet AS p "
            "JOIN dbo.tutor AS t ON t.id_tutor = p.id_tutor "
            "WHERE p.id_pet = ?",
            id_pet,
        )
        return cur.fetchone()


# ======================================================================
# ETAPA 4 — Relacionamento N:M consulta <-> procedimento
# ======================================================================
STATUS_CONSULTA = {"AGENDADA", "REALIZADA", "CANCELADA"}


def _normalizar_itens(procedimentos):
    """Aceita [id, id, ...] ou [(id, quantidade), ...] e devolve [(id, qtd)]."""
    itens = []
    for item in procedimentos or []:
        if isinstance(item, int):
            itens.append((item, 1))
            continue
        try:
            id_proc, quantidade = item
        except (TypeError, ValueError):
            raise DadoInvalido(
                "Cada procedimento deve ser um id ou uma tupla (id, quantidade)."
            ) from None
        itens.append((id_proc, quantidade))
    return itens


def _inserir_item(cur, id_consulta, id_procedimento, quantidade):
    """Insere o item cobrando o preco_base ATUAL do procedimento."""
    cur.execute(
        "INSERT INTO dbo.consulta_procedimento "
        "(id_consulta, id_procedimento, quantidade, valor_cobrado) "
        "SELECT ?, id_procedimento, ?, preco_base "
        "FROM dbo.procedimento WHERE id_procedimento = ?",
        id_consulta, quantidade, id_procedimento,
    )
    if cur.rowcount == 0:
        raise RegistroNaoEncontrado(f"Procedimento {id_procedimento} não existe.")


def _exigir_consulta_ativa(cur, id_consulta):
    """Garante que a consulta existe e não está cancelada."""
    cur.execute(
        "SELECT status FROM dbo.consulta WITH (UPDLOCK) WHERE id_consulta = ?",
        id_consulta,
    )
    linha = cur.fetchone()
    if linha is None:
        raise RegistroNaoEncontrado("Consulta não encontrada.")
    if linha.status == "CANCELADA":
        raise OperacaoBloqueada("Consulta cancelada não pode ter procedimentos alterados.")


@_tratar_erros
def agendar_consulta(id_pet, id_vet, data_hora, motivo, procedimentos=()) -> int:
    """Grava a consulta e seus itens na MESMA transação: se um item falhar,
    nada é gravado. Devolve o id_consulta.

    procedimentos: lista de ids ou de tuplas (id_procedimento, quantidade).
    """
    itens = _normalizar_itens(procedimentos)
    with transacao() as cur:
        cur.execute(
            "INSERT INTO dbo.consulta (id_pet, id_veterinario, data_hora, motivo, status) "
            "OUTPUT INSERTED.id_consulta VALUES (?, ?, ?, ?, 'AGENDADA')",
            id_pet, id_vet, data_hora, motivo,
        )
        id_consulta = cur.fetchone()[0]
        for id_proc, quantidade in itens:
            _inserir_item(cur, id_consulta, id_proc, quantidade)
        return id_consulta


@_tratar_erros
def adicionar_procedimento(id_consulta, id_procedimento, quantidade=1):
    """Acrescenta um item. Erro se o item já existe ou a consulta está cancelada."""
    with transacao() as cur:
        _exigir_consulta_ativa(cur, id_consulta)
        _inserir_item(cur, id_consulta, id_procedimento, quantidade)


@_tratar_erros
def remover_procedimento(id_consulta, id_procedimento):
    """Remove um item. Erro se o item não existe ou a consulta está cancelada."""
    with transacao() as cur:
        _exigir_consulta_ativa(cur, id_consulta)
        cur.execute(
            "DELETE FROM dbo.consulta_procedimento "
            "WHERE id_consulta = ? AND id_procedimento = ?",
            id_consulta, id_procedimento,
        )
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Esse procedimento não está na consulta.")


@_tratar_erros
def listar_procedimentos_da_consulta(id_consulta):
    """N:M no sentido consulta -> procedimentos."""
    with transacao() as cur:
        cur.execute(
            "SELECT pr.id_procedimento, pr.descricao, cp.quantidade, cp.valor_cobrado, "
            "       cp.quantidade * cp.valor_cobrado AS subtotal "
            "FROM dbo.consulta_procedimento AS cp "
            "JOIN dbo.procedimento AS pr ON pr.id_procedimento = cp.id_procedimento "
            "WHERE cp.id_consulta = ? ORDER BY pr.descricao",
            id_consulta,
        )
        return cur.fetchall()


@_tratar_erros
def listar_consultas_por_procedimento(id_procedimento):
    """N:M no sentido procedimento -> consultas."""
    with transacao() as cur:
        cur.execute(
            "SELECT c.id_consulta, c.data_hora, c.status, p.nome AS pet, "
            "       v.nome AS veterinario, cp.quantidade, cp.valor_cobrado "
            "FROM dbo.consulta_procedimento AS cp "
            "JOIN dbo.consulta AS c ON c.id_consulta = cp.id_consulta "
            "JOIN dbo.pet AS p ON p.id_pet = c.id_pet "
            "JOIN dbo.veterinario AS v ON v.id_veterinario = c.id_veterinario "
            "WHERE cp.id_procedimento = ? ORDER BY c.data_hora",
            id_procedimento,
        )
        return cur.fetchall()


@_tratar_erros
def total_da_consulta(id_consulta):
    """Soma quantidade * valor_cobrado dos itens (0 se não houver itens)."""
    with transacao() as cur:
        cur.execute(
            "SELECT ISNULL(SUM(cp.quantidade * cp.valor_cobrado), 0) AS total "
            "FROM dbo.consulta AS c "
            "LEFT JOIN dbo.consulta_procedimento AS cp ON cp.id_consulta = c.id_consulta "
            "WHERE c.id_consulta = ? GROUP BY c.id_consulta",
            id_consulta,
        )
        linha = cur.fetchone()
        if linha is None:
            raise RegistroNaoEncontrado("Consulta não encontrada.")
        return linha.total


@_tratar_erros
def atualizar_status_consulta(id_consulta, novo_status):
    status = (novo_status or "").upper()
    if status not in STATUS_CONSULTA:
        raise DadoInvalido("Status inválido. Use AGENDADA, REALIZADA ou CANCELADA.")
    with transacao() as cur:
        cur.execute(
            "UPDATE dbo.consulta SET status = ? WHERE id_consulta = ?",
            status, id_consulta,
        )
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Consulta não encontrada.")


@_tratar_erros
def excluir_consulta(id_consulta):
    """Exclui a consulta; os itens somem por ON DELETE CASCADE."""
    with transacao() as cur:
        cur.execute("DELETE FROM dbo.consulta WHERE id_consulta = ?", id_consulta)
        if cur.rowcount == 0:
            raise RegistroNaoEncontrado("Consulta não encontrada.")


# ======================================================================
# BÔNUS
# ======================================================================
@_tratar_erros
def historico_do_pet(id_pet):
    """Consultas do pet usando a view vw_resumo_consulta.
    A view não expõe id_pet, então filtramos por JOIN com dbo.consulta."""
    with transacao() as cur:
        cur.execute(
            "SELECT v.* FROM dbo.vw_resumo_consulta AS v "
            "JOIN dbo.consulta AS c ON c.id_consulta = v.id_consulta "
            "WHERE c.id_pet = ? ORDER BY v.data_hora DESC",
            id_pet,
        )
        return cur.fetchall()
