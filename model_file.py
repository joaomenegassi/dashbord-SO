import time
from pathlib import Path
from datetime import datetime
import os
import stat
from model_system import get_username_from_uid_local # Importa a função para obter o nome de usuário

def get_filesystem_info():
    """
    Coleta informações do sistema de arquivos, incluindo partições e seu uso.
    Filtra partições "inúteis" para focar nas principais.
    Lê de /proc/mounts para identificar pontos de montagem e usa os.statvfs para obter
    estatísticas de uso (tamanho total, usado, livre) para cada ponto de montagem.

    Returns:
        dict: Um dicionário contendo informações das partições.
              Ex: {"partitions": [{"name": "/dev/sda1", "mount_point": "/", ...}], "last_update": ...}
    """
    partitions_info = []
    try:
        # Define tipos de sistema de arquivos e pontos de montagem a serem ignorados.
        fs_types_to_ignore = [
            "sysfs", "proc", "devtmpfs", "tmpfs", "devpts", "debugfs",
            "securityfs", "fusectl", "cgroup", "overlay", "autofs",
            "mqueue", "hugetlbfs", "pstore", "rpc_pipefs", "binfmt_misc",
            "none", "configfs"
        ]
        mount_points_to_ignore_prefix = [
            "/sys", "/proc", "/dev", "/run", "/var/lib/docker", "/snap", "/etc/resolv.conf",
            "/etc/hostname", "/etc/hosts"
        ]

        # Lê /proc/mounts para obter os pontos de montagem
        with (Path('/proc') / 'mounts').open('r', encoding='utf-8') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue

                device_name = parts[0]
                mount_point_str = parts[1]
                fs_type = parts[2]

                if fs_type in fs_types_to_ignore:
                    continue

                if any(mount_point_str.startswith(prefix) for prefix in mount_points_to_ignore_prefix):
                    continue

                if not device_name.startswith("/dev") and device_name not in ["rootfs", "tmpfs"]:
                     if fs_type == "tmpfs" and not any(mount_point_str.startswith(prefix) for prefix in ["/dev/shm", "/run/user"]):
                         pass
                     else:
                         continue

                try:
                    # Usa os.statvfs para obter estatísticas do sistema de arquivos
                    stat_info = os.statvfs(mount_point_str)

                    total_size_bytes = stat_info.f_blocks * stat_info.f_frsize
                    free_bytes = stat_info.f_bavail * stat_info.f_frsize
                    used_bytes = total_size_bytes - free_bytes

                    total_size_kb = total_size_bytes / 1024
                    used_kb = used_bytes / 1024
                    free_kb = free_bytes / 1024

                    usage_percent = (used_bytes / total_size_bytes) * 100 if total_size_bytes > 0 else 0.0

                    if total_size_kb <= 0:
                        continue

                    partitions_info.append({
                        "name": device_name,
                        "mount_point": mount_point_str,
                        "fs_type": fs_type,
                        "total_size_kb": round(total_size_kb, 2),
                        "used_kb": round(used_kb, 2),
                        "free_kb": round(free_kb, 2),
                        "usage_percent": round(usage_percent, 2)
                    })
                except FileNotFoundError:
                    continue
                except PermissionError:
                    continue
                except Exception as e:
                    print(f"Erro ao obter informações para {mount_point_str}: {e}")
                    continue

    except FileNotFoundError:
        print("Aviso: /proc/mounts não encontrado. Não foi possível coletar informações de partição.")
    except Exception as e:
        print(f"Erro ao ler /proc/mounts: {e}")

    return {
        "partitions": partitions_info,
        "last_update": time.time()
    }


def get_directory_contents(path_str):
    """
    Lista os arquivos e subdiretórios de um dado caminho, incluindo seus atributos.
    Utiliza pathlib.Path para manipulação de caminhos e os.stat para obter atributos,
    que são wrappers para chamadas de sistema diretas.

    Args:
        path_str (str): O caminho do diretório a ser listado.

    Returns:
        list: Uma lista de dicionários, onde cada dicionário representa um item (arquivo ou diretório)
              com seus atributos (nome, tipo, tamanho, permissões, data de modificação, proprietário).
              Retorna uma lista vazia e imprime um erro se o caminho for inválido ou inacessível.
    """
    contents = []
    current_path = Path(path_str)

    try:
        if not current_path.is_dir():
            print(f"Erro: O caminho '{path_str}' não é um diretório ou não existe.")
            return []

        for item_path in current_path.iterdir():
            item_name = item_path.name

            item_info = {
                "name": item_name,
                "type": "N/A",
                "size": "N/A",
                "permissions_octal": "N/A", # Mantido no modelo, mas não será exibido na view
                "permissions_str": "N/A",
                "last_modified": "N/A",
                "owner_username": "N/A", # Adicionada a nova chave para o nome do proprietário
                "full_path": str(item_path)
            }

            try:
                s = item_path.stat()

                item_type = "Desconhecido"
                if stat.S_ISDIR(s.st_mode):
                    item_type = "Diretório"
                elif stat.S_ISREG(s.st_mode):
                    item_type = "Arquivo"
                elif stat.S_ISLNK(s.st_mode):
                    item_type = "Link Simbólico"
                elif stat.S_ISCHR(s.st_mode):
                    item_type = "Dispositivo de Caractere"
                elif stat.S_ISBLK(s.st_mode):
                    item_type = "Dispositivo de Bloco"
                elif stat.S_ISFIFO(s.st_mode):
                    item_type = "FIFO (Pipe Nomeado)"
                elif stat.S_ISSOCK(s.st_mode):
                    item_type = "Socket"

                permissions_octal = oct(s.st_mode & 0o777)
                permissions_str = stat.filemode(s.st_mode)
                size = s.st_size if item_type == "Arquivo" else "N/A"
                last_modified = datetime.fromtimestamp(s.st_mtime).strftime('%d/%m/%Y %H:%M:%S')

                # Obtém o nome de usuário a partir do UID do arquivo
                owner_username = get_username_from_uid_local(s.st_uid)

                item_info.update({
                    "type": item_type,
                    "size": size,
                    "permissions_octal": permissions_octal,
                    "permissions_str": permissions_str,
                    "last_modified": last_modified,
                    "owner_username": owner_username # Adiciona o nome do proprietário
                })

            except FileNotFoundError:
                item_info.update({"type": "N/A (Não Encontrado)"})
            except PermissionError:
                item_info.update({"type": "N/A (Permissão Negada)"})
            except Exception as e:
                print(f"Erro ao obter detalhes de '{item_path}': {e}")
                item_info.update({"type": "N/A (Erro)"})
            finally:
                contents.append(item_info)

    except PermissionError:
        print(f"Erro de permissão: Não foi possível listar o diretório '{path_str}'.")
        return []
    except Exception as e:
        print(f"Erro inesperado ao listar diretório '{path_str}': {e}")
        return []
    return contents