# Dashboard de Monitoramento de Sistema

Este projeto implementa um Dashboard de Monitoramento de Sistema completo, desenvolvido em Python, com o objetivo de oferecer uma visão detalhada e em tempo real sobre o estado do sistema operacional. Ele foi concebido como um projeto acadêmico focado em demonstrar a aquisição e processamento de dados do sistema, seguindo padrões de design como MVC e utilizando programação multitarefa.

## Objetivos e Funcionalidades Principais

O Dashboard abrange as seguintes áreas de monitoramento:

### 1. Monitoramento de Processos e Uso de CPU
* **Visão Geral do Sistema:** Apresenta dados globais sobre o uso do processador (percentual de uso, tempo ocioso), quantidade total de processos e threads ativos.
* **Lista de Processos:** Exibe uma lista abrangente dos processos em execução, incluindo PID, nome, usuário proprietário, percentual de uso de CPU, tempo de CPU acumulado, número de threads, uso de memória e taxas de I/O de disco (leitura/escrita).
* **Detalhes de Processos:** Permite visualizar informações detalhadas de um processo específico (por PID), como estado, prioridade, nice value, horário de início, e dados de I/O.

### 2. Monitoramento de Memória
* **Uso Global de Memória:** Mostra dados globais do uso de memória do sistema, incluindo percentual de memória utilizada, memória livre, quantidade de memória física (RAM) e virtual (SWAP).
* **Uso de Memória por Processo:** Fornece informações detalhadas sobre o uso de memória para cada processo, como memória residente (VmRSS), memória virtual (VmSize), e a quantidade de páginas de memória (total, código, heap, stack).

### 3. Monitoramento do Sistema de Arquivos
* **Informações de Partições:** Apresenta dados sobre as partições do sistema, incluindo pontos de montagem, tipo de sistema de arquivos, tamanho total, espaço usado, espaço livre e percentual de uso de cada partição.
* **Navegação de Diretórios:** Permite navegar na árvore de diretórios do sistema de arquivos, a partir da raiz.
* **Listagem de Arquivos:** Lista os arquivos contidos em um diretório específico, juntamente com seus atributos (nome, tamanho, tipo, permissões, data de modificação e proprietário).

## Requisitos e Arquitetura

O projeto foi desenvolvido seguindo os seguintes requisitos e princípios arquiteturais:

* **Atualização Regular:** As informações são atualizadas automaticamente em intervalos regulares (a cada 3 segundos, configurável).
* **Dados Processados:** A informação apresentada é "processada" pelo Dashboard, não sendo a saída "crua" de comandos do sistema operacional.
* **Uso de APIs do Sistema Operacional:** A obtenção das informações é feita diretamente via APIs do sistema operacional (leitura de arquivos como `/proc/stat`, `/proc/meminfo`, `/proc/[pid]/stat`, `/proc/[pid]/status`, `/proc/[pid]/io`, `/proc/[pid]/fd`, `/proc/diskstats`, `/proc/mounts`, e funções `os.statvfs`, `os.readlink`, `Path.iterdir`, `Path.stat`), sem o uso de comandos de shell (ex: `ps`, `df`).
* **Multitarefa:** Implementado como um software multitarefa, utilizando threads para separar a aquisição, o processamento e a apresentação dos dados, seguindo o padrão de projeto MVC (Model-View-Controller).

## Como Usar

Para executar o dashboard, siga os passos abaixo:

### Pré-requisitos
* Python 3.8+ (recomendado) instalado.
* Conexão à internet para baixar as dependências (somente na primeira vez).

### 1. Preparar o Ambiente (Opcional, mas Altamente Recomendado)

É uma boa prática utilizar um ambiente virtual para isolar as dependências do projeto do seu sistema global.

```bash
python3 -m venv venv_dashboard
source venv_dashboard/bin/activate  # No Linux/macOS
# No Windows, use: .\venv_dashboard\Scripts\activate