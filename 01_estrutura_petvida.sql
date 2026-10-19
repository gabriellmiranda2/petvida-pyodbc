/* =====================================================================
   DESAFIO TÉCNICO — Conexão Python + SQL Server com pyodbc
   Banco de dados: PetVida (Clínica Veterinária)
   Script: estrutura completa + dados iniciais
   Compatível com: SQL Server 2019/2022/2025 (inclui Express e Developer)
   Arquivo salvo em UTF-8 com BOM (acentos corretos no SSMS).
   Execute no SSMS, Azure Data Studio ou sqlcmd.
   ===================================================================== */

USE master;
GO

IF DB_ID('PetVida') IS NOT NULL
BEGIN
    ALTER DATABASE PetVida SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE PetVida;
END
GO

CREATE DATABASE PetVida;
GO

USE PetVida;
GO

/* ---------------------------------------------------------------------
   1. TUTOR  (lado "1" do relacionamento TUTOR 1 —— N PET)
   --------------------------------------------------------------------- */
CREATE TABLE dbo.tutor (
    id_tutor      INT IDENTITY(1,1)  NOT NULL,
    nome          NVARCHAR(120)      NOT NULL,
    cpf           CHAR(11)           NOT NULL,
    email         NVARCHAR(120)      NULL,
    telefone      VARCHAR(20)        NULL,
    data_cadastro DATETIME2(0)       NOT NULL CONSTRAINT df_tutor_data DEFAULT (SYSDATETIME()),
    CONSTRAINT pk_tutor     PRIMARY KEY (id_tutor),
    CONSTRAINT uq_tutor_cpf UNIQUE (cpf),
    CONSTRAINT ck_tutor_cpf CHECK (cpf NOT LIKE '%[^0-9]%' AND LEN(cpf) = 11)
);
GO

/* ---------------------------------------------------------------------
   2. PET  (lado "N" de TUTOR; lado "1" de CONSULTA)
   Excluir um tutor com pets é BLOQUEADO (NO ACTION) — regra de negócio
   que o código Python deverá tratar.
   --------------------------------------------------------------------- */
CREATE TABLE dbo.pet (
    id_pet          INT IDENTITY(1,1) NOT NULL,
    id_tutor        INT               NOT NULL,
    nome            NVARCHAR(60)      NOT NULL,
    especie         NVARCHAR(20)      NOT NULL,
    raca            NVARCHAR(60)      NULL,
    data_nascimento DATE              NULL,
    peso_kg         DECIMAL(5,2)      NULL,
    CONSTRAINT pk_pet        PRIMARY KEY (id_pet),
    CONSTRAINT fk_pet_tutor  FOREIGN KEY (id_tutor) REFERENCES dbo.tutor (id_tutor),
    CONSTRAINT ck_pet_especie CHECK (especie IN (N'Cão', N'Gato', N'Ave', N'Roedor', N'Réptil', N'Outro')),
    CONSTRAINT ck_pet_peso   CHECK (peso_kg IS NULL OR peso_kg > 0)
);
GO
CREATE INDEX ix_pet_tutor ON dbo.pet (id_tutor);
GO

/* ---------------------------------------------------------------------
   3. VETERINÁRIO  (lado "1" de CONSULTA)
   --------------------------------------------------------------------- */
CREATE TABLE dbo.veterinario (
    id_veterinario INT IDENTITY(1,1) NOT NULL,
    nome           NVARCHAR(120)     NOT NULL,
    crmv           VARCHAR(15)       NOT NULL,
    especialidade  NVARCHAR(60)      NULL,
    ativo          BIT               NOT NULL CONSTRAINT df_vet_ativo DEFAULT (1),
    CONSTRAINT pk_veterinario PRIMARY KEY (id_veterinario),
    CONSTRAINT uq_vet_crmv    UNIQUE (crmv)
);
GO

/* ---------------------------------------------------------------------
   4. PROCEDIMENTO  (catálogo de serviços — um lado do N:M)
   --------------------------------------------------------------------- */
CREATE TABLE dbo.procedimento (
    id_procedimento INT IDENTITY(1,1) NOT NULL,
    descricao       NVARCHAR(100)     NOT NULL,
    preco_base      DECIMAL(10,2)     NOT NULL,
    CONSTRAINT pk_procedimento PRIMARY KEY (id_procedimento),
    CONSTRAINT uq_proc_desc    UNIQUE (descricao),
    CONSTRAINT ck_proc_preco   CHECK (preco_base >= 0)
);
GO

/* ---------------------------------------------------------------------
   5. CONSULTA  (N para PET e N para VETERINÁRIO — outro lado do N:M)
   --------------------------------------------------------------------- */
CREATE TABLE dbo.consulta (
    id_consulta    INT IDENTITY(1,1) NOT NULL,
    id_pet         INT               NOT NULL,
    id_veterinario INT               NOT NULL,
    data_hora      DATETIME2(0)      NOT NULL,
    motivo         NVARCHAR(200)     NOT NULL,
    status         VARCHAR(15)       NOT NULL CONSTRAINT df_consulta_status DEFAULT ('AGENDADA'),
    observacoes    NVARCHAR(MAX)     NULL,
    CONSTRAINT pk_consulta       PRIMARY KEY (id_consulta),
    CONSTRAINT fk_consulta_pet   FOREIGN KEY (id_pet)         REFERENCES dbo.pet (id_pet),
    CONSTRAINT fk_consulta_vet   FOREIGN KEY (id_veterinario) REFERENCES dbo.veterinario (id_veterinario),
    CONSTRAINT ck_consulta_status CHECK (status IN ('AGENDADA', 'REALIZADA', 'CANCELADA'))
);
GO
CREATE INDEX ix_consulta_pet ON dbo.consulta (id_pet);
CREATE INDEX ix_consulta_vet ON dbo.consulta (id_veterinario);
GO

/* ---------------------------------------------------------------------
   6. CONSULTA_PROCEDIMENTO  (tabela associativa — CONSULTA N —— M PROCEDIMENTO)
   Guarda atributos do relacionamento: quantidade e valor efetivamente cobrado.
   Excluir uma consulta remove seus itens (CASCADE).
   --------------------------------------------------------------------- */
CREATE TABLE dbo.consulta_procedimento (
    id_consulta     INT           NOT NULL,
    id_procedimento INT           NOT NULL,
    quantidade      INT           NOT NULL CONSTRAINT df_cp_qtd DEFAULT (1),
    valor_cobrado   DECIMAL(10,2) NOT NULL,
    CONSTRAINT pk_consulta_procedimento PRIMARY KEY (id_consulta, id_procedimento),
    CONSTRAINT fk_cp_consulta     FOREIGN KEY (id_consulta)     REFERENCES dbo.consulta (id_consulta) ON DELETE CASCADE,
    CONSTRAINT fk_cp_procedimento FOREIGN KEY (id_procedimento) REFERENCES dbo.procedimento (id_procedimento),
    CONSTRAINT ck_cp_qtd   CHECK (quantidade > 0),
    CONSTRAINT ck_cp_valor CHECK (valor_cobrado >= 0)
);
GO

/* ---------------------------------------------------------------------
   7. VIEW de apoio — resumo financeiro por consulta
   --------------------------------------------------------------------- */
CREATE VIEW dbo.vw_resumo_consulta AS
SELECT  c.id_consulta,
        c.data_hora,
        c.status,
        p.nome               AS pet,
        t.nome               AS tutor,
        v.nome               AS veterinario,
        COUNT(cp.id_procedimento)                         AS qtd_itens,
        ISNULL(SUM(cp.quantidade * cp.valor_cobrado), 0)  AS valor_total
FROM dbo.consulta c
JOIN dbo.pet         p ON p.id_pet         = c.id_pet
JOIN dbo.tutor       t ON t.id_tutor       = p.id_tutor
JOIN dbo.veterinario v ON v.id_veterinario = c.id_veterinario
LEFT JOIN dbo.consulta_procedimento cp ON cp.id_consulta = c.id_consulta
GROUP BY c.id_consulta, c.data_hora, c.status, p.nome, t.nome, v.nome;
GO

/* =====================================================================
   DADOS INICIAIS
   ===================================================================== */
INSERT INTO dbo.tutor (nome, cpf, email, telefone) VALUES
 (N'Ana Beatriz Souza',   '12345678901', 'ana.souza@email.com',   '(17) 99111-2233'),
 (N'Carlos Eduardo Lima', '23456789012', 'carlos.lima@email.com', '(17) 99222-3344'),
 (N'Juliana Martins',     '34567890123', 'ju.martins@email.com',  '(17) 99333-4455'),
 (N'Roberto Almeida',     '45678901234', NULL,                    '(17) 99444-5566');

INSERT INTO dbo.pet (id_tutor, nome, especie, raca, data_nascimento, peso_kg) VALUES
 (1, N'Thor', N'Cão',    N'Golden Retriever', '2019-03-10', 32.50),
 (1, N'Mia', N'Gato',   N'Siamês',           '2021-07-22',  4.10),
 (2, N'Bolinha', N'Cão',    N'Shih Tzu',         '2020-01-05',  6.80),
 (3, N'Kiwi', N'Ave',    N'Calopsita',        '2022-11-30',  0.09),
 (3, N'Luna', N'Gato',   N'SRD',              '2018-05-14',  5.30),
 (3, N'Pipoca', N'Roedor', N'Hamster Sírio',    '2024-02-01',  0.15);
-- Tutor 4 (Roberto) propositalmente sem pets: pode ser excluído.

INSERT INTO dbo.veterinario (nome, crmv, especialidade) VALUES
 (N'Dra. Fernanda Rocha', 'SP-12345', N'Clínica Geral'),
 (N'Dr. Marcelo Tavares', 'SP-23456', N'Dermatologia'),
 (N'Dra. Patrícia Nunes', 'SP-34567', N'Animais Silvestres');

INSERT INTO dbo.procedimento (descricao, preco_base) VALUES
 (N'Consulta clínica',          150.00),
 (N'Vacina V10',                 90.00),
 (N'Vacina antirrábica',         60.00),
 (N'Hemograma completo',        110.00),
 (N'Banho medicamentoso',        80.00),
 (N'Aplicação de vermífugo',     35.00),
 (N'Corte de unhas',             25.00);

INSERT INTO dbo.consulta (id_pet, id_veterinario, data_hora, motivo, status, observacoes) VALUES
 (1, 1, '2026-09-02 09:00', N'Vacinação anual',        'REALIZADA', N'Animal saudável.'),
 (3, 2, '2026-09-05 14:30', N'Coceira persistente',    'REALIZADA', N'Suspeita de dermatite alérgica.'),
 (4, 3, '2026-09-10 10:00', N'Corte de unhas e check-up','REALIZADA', NULL),
 (2, 1, '2026-10-20 16:00', N'Vermifugação',           'AGENDADA',  NULL),
 (5, 1, '2026-10-22 11:00', N'Exames de rotina',       'AGENDADA',  NULL);

INSERT INTO dbo.consulta_procedimento (id_consulta, id_procedimento, quantidade, valor_cobrado) VALUES
 (1, 1, 1, 150.00),
 (1, 2, 1,  90.00),
 (1, 3, 1,  60.00),
 (2, 1, 1, 150.00),
 (2, 5, 2,  75.00),   -- 2 banhos com desconto
 (2, 4, 1, 110.00),
 (3, 1, 1, 120.00),
 (3, 7, 1,  25.00);
GO

/* ---------------------------------------------------------------------
   8. (OPCIONAL) Login SQL dedicado para a aplicação Python
   Requer autenticação mista habilitada na instância
   (SSMS > Propriedades do servidor > Segurança > "SQL Server and Windows Authentication").
   --------------------------------------------------------------------- */
/*
USE master;
CREATE LOGIN petvida_app WITH PASSWORD = 'PetVida@2026!', CHECK_POLICY = ON;
GO
USE PetVida;
CREATE USER petvida_app FOR LOGIN petvida_app;
ALTER ROLE db_datareader ADD MEMBER petvida_app;
ALTER ROLE db_datawriter ADD MEMBER petvida_app;
GO
*/

/* Conferência rápida */
SELECT * FROM dbo.vw_resumo_consulta ORDER BY data_hora;
GO
