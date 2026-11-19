-- Falha se alguma tabela do schema public nao tiver chave primaria.
-- Roda na CI depois do ciclo de migrations, com psql -v ON_ERROR_STOP=1.
-- Motivo: a perda da PK de mensagens passou sem alerta (secao 0 de
-- docs/diagnosticos/2026-11-18-plano-rodada3.md).
DO $$
DECLARE
    sem_pk text;
BEGIN
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
    INTO sem_pk
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND NOT EXISTS (
          SELECT 1 FROM pg_constraint k
          WHERE k.conrelid = c.oid AND k.contype = 'p'
      );
    IF sem_pk IS NOT NULL THEN
        RAISE EXCEPTION 'tabelas sem chave primaria: %', sem_pk;
    END IF;
    RAISE NOTICE 'todas as tabelas de public tem chave primaria';
END
$$;
