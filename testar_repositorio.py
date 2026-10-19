"""Teste de fumaça do repositório PetVida.

Roda contra o banco real e mostra OK/FALHA para cada regra da atividade.
Os registros criados aqui são apagados no final. Para voltar ao estado
original a qualquer momento, execute de novo 01_estrutura_petvida.sql.

Uso:  python testar_repositorio.py
"""
import random
import sys
from datetime import datetime

import db
import repositorio as repo

resultados = []


def verificar(descricao, condicao):
    resultados.append(bool(condicao))
    print(f"[{'OK' if condicao else 'FALHA'}] {descricao}")


def exige_erro(descricao, classe, funcao, *args, **kwargs):
    try:
        funcao(*args, **kwargs)
    except classe as e:
        print(f"[OK] {descricao} -> {classe.__name__}: {e}")
        resultados.append(True)
    except Exception as e:  # erro de outra classe
        print(f"[FALHA] {descricao} -> esperava {classe.__name__}, veio {type(e).__name__}: {e}")
        resultados.append(False)
    else:
        print(f"[FALHA] {descricao} -> nenhum erro foi lançado")
        resultados.append(False)


def contar(tabela_sql):
    with db.transacao() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {tabela_sql}")  # constante interna, não vem do usuário
        return cur.fetchone()[0]


def main():
    info = db.testar_conexao()
    verificar(f"Conexão com o banco PetVida ({info['servidor']})", info["banco"] == "PetVida")

    print("\n--- Segurança ---")
    verificar("SQL Injection no filtro não retorna tutores",
              repo.listar_tutores("' OR 1=1 --") == [])

    print("\n--- Etapa 2: tutor ---")
    cpf = "".join(random.choice("0123456789") for _ in range(11))
    id_tutor = repo.criar_tutor("Tutor de Teste", cpf, "teste@email.com", "(17) 90000-0000")
    verificar("criar_tutor devolve o id gerado (OUTPUT INSERTED)", isinstance(id_tutor, int))
    verificar("buscar_tutor encontra o tutor criado", repo.buscar_tutor(id_tutor).nome == "Tutor de Teste")
    verificar("buscar_tutor devolve None se não existe", repo.buscar_tutor(999999) is None)
    verificar("listar_tutores filtra por nome", any(t.id_tutor == id_tutor for t in repo.listar_tutores("de Teste")))
    exige_erro("CPF duplicado", repo.RegistroDuplicado, repo.criar_tutor, "Outro", cpf)
    exige_erro("CPF com 10 dígitos", repo.DadoInvalido, repo.criar_tutor, "Outro", "1234567890")
    exige_erro("CPF com letras", repo.DadoInvalido, repo.criar_tutor, "Outro", "abcdefghijk")
    repo.atualizar_tutor(id_tutor, nome="Tutor Renomeado", telefone=None)
    verificar("atualizar_tutor altera nome e telefone", repo.buscar_tutor(id_tutor).nome == "Tutor Renomeado")
    exige_erro("atualizar_tutor recusa campo fora da lista branca", repo.DadoInvalido,
               repo.atualizar_tutor, id_tutor, cpf="00000000000")
    exige_erro("atualizar tutor inexistente", repo.RegistroNaoEncontrado,
               repo.atualizar_tutor, 999999, nome="X")

    print("\n--- Etapa 3: tutor -> pet (1:N) ---")
    id_pet = repo.criar_pet(id_tutor, "Rex de Teste", "Cão", "SRD", None, 10.5)
    verificar("criar_pet devolve o id gerado", isinstance(id_pet, int))
    exige_erro("espécie fora da lista", repo.DadoInvalido, repo.criar_pet, id_tutor, "X", "Dragão")
    exige_erro("peso negativo", repo.DadoInvalido, repo.criar_pet, id_tutor, "X", "Cão", None, None, -1)
    exige_erro("pet para tutor inexistente", repo.RegistroNaoEncontrado, repo.criar_pet, 999999, "X", "Cão")
    repo.atualizar_peso_pet(id_pet, 11.2)
    verificar("atualizar_peso_pet", float(repo.buscar_pet_com_tutor(id_pet).peso_kg) == 11.2)
    exige_erro("transferir para tutor inexistente", repo.RegistroNaoEncontrado, repo.transferir_pet, id_pet, 999999)
    repo.transferir_pet(id_pet, 1)
    verificar("transferir_pet muda o tutor", repo.buscar_pet_com_tutor(id_pet).id_tutor == 1)
    repo.transferir_pet(id_pet, id_tutor)
    verificar("listar_pets_do_tutor (1 -> N)", [p.id_pet for p in repo.listar_pets_do_tutor(id_tutor)] == [id_pet])
    verificar("buscar_pet_com_tutor (N -> 1, JOIN)", repo.buscar_pet_com_tutor(id_pet).nome_tutor == "Tutor Renomeado")
    exige_erro("excluir tutor que ainda tem pets", repo.OperacaoBloqueada, repo.excluir_tutor, id_tutor)
    exige_erro("excluir pet com consultas (Thor, id 1)", repo.OperacaoBloqueada, repo.excluir_pet, 1)

    print("\n--- Etapa 4: consulta <-> procedimento (N:M) ---")
    quando = datetime(2026, 12, 1, 10, 0)
    antes = contar("dbo.consulta")
    exige_erro("agendar com procedimento inexistente", repo.RegistroNaoEncontrado,
               repo.agendar_consulta, id_pet, 1, quando, "Teste", [(1, 1), (999, 1)])
    verificar("... e nada foi gravado (rollback)", contar("dbo.consulta") == antes)
    id_cons = repo.agendar_consulta(id_pet, 1, quando, "Teste", [(1, 1), (2, 2)])
    verificar("agendar_consulta grava consulta + itens", len(repo.listar_procedimentos_da_consulta(id_cons)) == 2)
    verificar("valor cobrado = preço base atual (150 + 2x90 = 330)", float(repo.total_da_consulta(id_cons)) == 330.0)
    exige_erro("item repetido", repo.RegistroDuplicado, repo.adicionar_procedimento, id_cons, 1)
    repo.adicionar_procedimento(id_cons, 4)
    verificar("adicionar_procedimento (+ hemograma 110 = 440)", float(repo.total_da_consulta(id_cons)) == 440.0)
    repo.remover_procedimento(id_cons, 4)
    verificar("remover_procedimento (volta a 330)", float(repo.total_da_consulta(id_cons)) == 330.0)
    exige_erro("remover item que não está na consulta", repo.RegistroNaoEncontrado, repo.remover_procedimento, id_cons, 7)
    verificar("listar_consultas_por_procedimento (N:M no outro sentido)",
              any(c.id_consulta == id_cons for c in repo.listar_consultas_por_procedimento(1)))
    verificar("historico_do_pet (view)", [h.id_consulta for h in repo.historico_do_pet(id_pet)] == [id_cons])
    exige_erro("status inválido", repo.DadoInvalido, repo.atualizar_status_consulta, id_cons, "TALVEZ")
    repo.atualizar_status_consulta(id_cons, "CANCELADA")
    exige_erro("adicionar a consulta cancelada", repo.OperacaoBloqueada, repo.adicionar_procedimento, id_cons, 3)
    exige_erro("remover de consulta cancelada", repo.OperacaoBloqueada, repo.remover_procedimento, id_cons, 1)
    repo.excluir_consulta(id_cons)
    verificar("excluir_consulta: itens somem em cascata (ON DELETE CASCADE)",
              repo.listar_procedimentos_da_consulta(id_cons) == [])
    exige_erro("total de consulta inexistente", repo.RegistroNaoEncontrado, repo.total_da_consulta, id_cons)

    print("\n--- Limpeza ---")
    repo.excluir_pet(id_pet)
    repo.excluir_tutor(id_tutor)
    verificar("pet e tutor de teste removidos", repo.buscar_tutor(id_tutor) is None)

    ok, total = sum(resultados), len(resultados)
    print(f"\nRESULTADO: {ok}/{total} verificações passaram.")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
