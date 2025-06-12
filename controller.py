import threading  # Importa o módulo para trabalhar com threads, permitindo a execução de tarefas em paralelo.
import time       # Importa o módulo para manipulação de tempo, usado aqui para `time.sleep`.
from model import get_global_info, get_processes_info  # Importa as funções do 'model.py' que buscam os dados brutos do sistema.

class SystemData:
    """
    Classe para armazenar e gerenciar os dados do sistema (informações globais e lista de processos).
    Utiliza um `threading.Lock` para garantir a segurança do acesso e modificação dos dados
    em ambientes multithread, prevenindo condições de corrida.
    """
    def __init__(self, limit=10):
        """
        Inicializa a instância SystemData.

        Args:
            limit (int): O número máximo de processos a serem armazenados na lista `self.processes`.
                         Este valor é usado pela função `get_processes_info`. O padrão é 10.
        """
        self.lock = threading.Lock()  # Cria um objeto Lock para sincronização de threads.
        # Dicionário para armazenar informações globais do sistema. Inicializado com valores padrão.
        self.global_info = {
            "CPU (%)": 0.0,
            "CPU ocioso (%)": 0.0,
            "Memória Usada (KB)": 0,
            "Memória (%)": 0.0,
            "Memória Livre (%)": 0.0,
            "Total de Processos": 0,
            "Total de Threads": 0,
            "Leitura Disco (B/s)": 0.0,
            "Escrita Disco (B/s)": 0.0
        }
        self.processes = []  # Lista para armazenar as informações dos processos.
        self.limit = limit  # Armazena o limite de processos a serem buscados.

    def update(self):
        """
        Atualiza as informações globais e a lista de processos.
        Este método é chamado periodicamente pela thread de coleta de dados (`background_data_collector`).
        Ele busca os dados mais recentes do sistema usando as funções `get_global_info` e `get_processes_info` do 'model.py'.
        """
        try:
            # Obtém as informações globais e dos processos do módulo 'model'.
            infos = get_global_info() # Chama a função do model para obter dados globais.
            procs = get_processes_info(self.limit)  # Chama a função do model para obter a lista de processos, passando o limite atual.

            # Adquire o lock antes de modificar os atributos `self.global_info` e `self.processes`.
            # Isso garante que a atualização dos dados seja segura, prevenindo que
            # outra thread (ex: a thread principal do Streamlit chamando `get_snapshot`) leia dados
            # parcialmente atualizados.
            with self.lock:
                self.global_info = infos # Atualiza as informações globais.
                self.processes = procs   # Atualiza a lista de processos.
        except Exception as e:
            print(f"[ERRO] Falha ao atualizar dados: {e}") 

    def get_snapshot(self):
        """
        Retorna uma cópia instantânea (snapshot) dos dados atuais do sistema.
        Utiliza o lock para garantir que a leitura dos dados (`self.global_info` e `self.processes`)
        seja segura.
        Retorna cópias dos dados (dicionário e lista) para evitar que modificações externas
        nos dados retornados afetem o estado interno do objeto `SystemData`.

        Returns:
            tuple: Uma tupla contendo (dicionário de informações globais, lista de processos).
                   Ex: ({'CPU (%)': 10.5, ...}, [{'pid': 1, ...}, ...])
        """
        with self.lock:  # Adquire o lock para ler os dados de forma segura.
            # Cria cópias dos dados para retornar:
            # - `self.global_info.copy()`: Cria uma cópia rasa do dicionário de informações globais.
            # - `list(self.processes)`: Cria uma cópia rasa da lista de processos.
            # Isso é importante porque, se retornássemos as referências diretas, a thread de atualização
            # poderia modificar os dados enquanto a thread principal (Streamlit) os está utilizando,
            # ou a thread principal poderia modificar os dados internos.
            current_global_info = self.global_info.copy() 
            current_processes = list(self.processes)
        return current_global_info, current_processes

# Instância global da classe SystemData.
# e também será importada e utilizada pelo `app.py` para obter os dados a serem exibidos.
system_data = SystemData() 

# Flag global para controlar se a thread de coleta de dados já foi iniciada.
# Isso garante que a thread `background_data_collector` seja iniciada apenas uma vez,
_thread_started = False 

def background_data_collector(interval):
    """
    Função alvo que será executada pela thread de coleta de dados.
    Executa em um loop infinito, chamando `system_data.update()` para atualizar
    os dados do sistema em intervalos regulares definidos por `interval`.

    Args:
        interval (int): O intervalo em segundos entre as atualizações de dados.
    """
    while True:  # Loop infinito para coleta contínua de dados.
        system_data.update()  # Chama o método update da instância global system_data para buscar novos dados.
        time.sleep(interval)  # Aguarda o tempo especificado antes da próxima coleta.

# Gerencia a criação e o início da thread de coleta de dados.
def start_background_thread(interval=5, limit=10):
    """
    Inicia a thread de coleta de dados em background, se ela ainda não tiver sido iniciada.
    Também atualiza o atributo `limit` da instância `system_data`, que define
    o número máximo de processos que a função `get_processes_info` (no model) deve buscar.

    Args:
        interval (int): O intervalo em segundos para a coleta de dados pela thread.
                        O valor padrão é 5 segundos, mas em `app.py` é chamado com 2 segundos.
        limit (int): O número máximo de processos a serem listados/coletados.
                     Este valor é passado para `system_data.limit`. Padrão é 10.
    """
    global _thread_started 

    # Atualiza o limite de processos no objeto `system_data`.
    # Isso permite que o número de processos coletados pela thread de background
    # seja dinamicamente ajustado pela interface do usuário em `app.py`.
    system_data.limit = limit

    # Verifica se a thread já foi iniciada para evitar criar múltiplas threads.
    if not _thread_started: #
        # Cria uma nova thread:
        # - `target=background_data_collector`: Especifica a função que a thread executará.
        # - `args=(interval,)`: Passa os argumentos para a função `target` (o intervalo de coleta).
        # - `daemon=True`: Define a thread como "daemon". Threads daemon são encerradas automaticamente
        #   quando o programa principal (a aplicação Streamlit, neste caso) termina. Isso evita que
        #   a thread de coleta continue rodando indefinidamente se o app for fechado.
        thread = threading.Thread(
            target=background_data_collector,
            args=(interval,),
            daemon=True
        )
        thread.start()  # Inicia a execução da thread.
        _thread_started = True # Define a flag para True para indicar que a thread foi iniciada e não deve ser iniciada novamente.