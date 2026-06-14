import argparse

def find_jobs_with_term(file_path, search_term):
    matched_jobs = []
    # Tenta abrir o arquivo com a codificação 'ISO-8859-1'
    with open(file_path, 'r', encoding='ISO-8859-1') as file:
        current_job = []
        collecting = False

        # Convertendo o termo de pesquisa para minúsculas
        search_term_lower = search_term.lower()

        for line in file:
            if 'BEGIN DSJOB' in line:
                collecting = True
                current_job = []
            if collecting:
                current_job.append(line)
            if 'END DSJOB' in line:
                collecting = False
                job_content = ''.join(current_job)
                
                # Tornando o conteúdo do job também em minúsculas para comparar sem considerar o case
                if search_term_lower in job_content.lower():  # Procurar o termo no conteúdo do job (case-insensitive)
                    # Encontrar o nome do job dentro do bloco
                    start_index = job_content.find('Name "') + len('Name "')
                    end_index = job_content[start_index:].find('"') + start_index
                    job_name = job_content[start_index:end_index]
                    matched_jobs.append(job_name)

    return matched_jobs

def main():
    # Configuração do argparse para obter os parâmetros
    parser = argparse.ArgumentParser(description="Pesquisar jobs do DataStage com base no nome de tabela, arquivo ou dataset.")
    parser.add_argument('file_path', help="Caminho do arquivo .dsx com os jobs do DataStage.")
    parser.add_argument('search_term', help="Termo a ser pesquisado (nome de tabela, arquivo, ou dataset) dentro dos jobs.")

    args = parser.parse_args()

    # Chama a função para encontrar os jobs que contêm o termo fornecido
    matched_jobs = find_jobs_with_term(args.file_path, args.search_term)

    if matched_jobs:
        print("Jobs encontrados com o termo '{}':".format(args.search_term))
        for job in matched_jobs:
            print(job)
    else:
        print("Nenhum job encontrado contendo o termo '{}'.".format(args.search_term))

# Inicia o script
if __name__ == "__main__":
    main()
