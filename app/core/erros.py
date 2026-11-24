"""Erros que nao se resolvem com nova tentativa do job (tarefa 5.4).

Cadastro da clinica invalido ou bug de carga nao mudam entre uma tentativa e outra.
Tentar de novo so atrasa as mensagens seguintes da conversa (ADR 0005). O worker
manda o job com um destes erros direto para dead e registra log de erro, porque o
problema e do sistema ou do cadastro, nao do paciente.
"""


class ErroPermanente(Exception):
    """Falha que se repetiria igual em qualquer nova tentativa do job."""
