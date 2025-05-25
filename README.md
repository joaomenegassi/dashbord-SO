# Dashboard de Monitoramento de Sistema

Este projeto é um dashboard feito em Python para mostrar informações sobre os processos e o uso de memória do sistema. Foi desenvolvido para fins de estudo.

## O que ele faz?

* Mostra um resumo do uso de CPU, memória RAM e atividade do disco.
* Lista os processos que estão rodando, com informações como PID, nome, quem iniciou, % de CPU e memória usada.
* Permite ver mais detalhes de um processo específico, como informações de memória mais detalhadas.
* Os dados são atualizados de tempos em tempos automaticamente.

## Como usar

Primeiro, você vai precisar do Python 3 instalado.

1.  **Prepare o ambiente (opcional, mas recomendado):**

    É uma boa ideia usar um ambiente virtual para não misturar as bibliotecas deste projeto com as do seu sistema.
    ```bash
    python3 -m venv meu_ambiente
    source meu_ambiente/bin/activate  # Para Linux ou macOS
    # Ou 'meu_ambiente\Scripts\activate' no Windows
    ```

2.  **Instale as bibliotecas necessárias:**

    Com o ambiente ativado (se você criou um), rode:
    ```bash
    pip install -r requirements.txt
    ```
    Se você tiver o `make` instalado, pode só rodar `make install`.

3.  **Execute o dashboard:**
    ```bash
    streamlit run app.py
    ```
    Ou, com `make`:
    ```bash
    make run
    ```
    Isso deve abrir o dashboard no seu navegador.

## Tecnologias

* Python
* Streamlit (para a interface web)
* Pandas (para ajudar com as tabelas)

---