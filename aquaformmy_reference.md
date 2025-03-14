# Referência do Aquaformmy

## Tipos de Dados (type)

### Numéricos
- `INT` - Número inteiro (-2147483648 a 2147483647)
- `INT UNSIGNED` - Número inteiro positivo (0 a 4294967295)
- `TINYINT` - Número inteiro pequeno (-128 a 127)
- `SMALLINT` - Número inteiro médio (-32768 a 32767)
- `MEDIUMINT` - Número inteiro médio-grande (-8388608 a 8388607)
- `BIGINT` - Número inteiro grande (-9223372036854775808 a 9223372036854775807)
- `DECIMAL(M,D)` - Número decimal exato (M dígitos totais, D casas decimais)
- `FLOAT` - Número decimal de precisão simples
- `DOUBLE` - Número decimal de precisão dupla

### Texto
- `CHAR(N)` - Texto de tamanho fixo (N caracteres)
- `VARCHAR(N)` - Texto de tamanho variável (até N caracteres)
- `TEXT` - Texto longo (até 65,535 caracteres)
- `MEDIUMTEXT` - Texto muito longo (até 16,777,215 caracteres)
- `LONGTEXT` - Texto extremamente longo (até 4,294,967,295 caracteres)
- `ENUM('valor1', 'valor2', ...)` - Lista de valores permitidos

### Data e Hora
- `DATE` - Data (YYYY-MM-DD)
- `TIME` - Hora (HH:MM:SS)
- `DATETIME` - Data e hora (YYYY-MM-DD HH:MM:SS)
- `TIMESTAMP` - Timestamp Unix (YYYY-MM-DD HH:MM:SS)
- `YEAR` - Ano (YYYY)

### Binários
- `BINARY(N)` - Binário de tamanho fixo
- `VARBINARY(N)` - Binário de tamanho variável
- `BLOB` - Binário longo
- `MEDIUMBLOB` - Binário muito longo
- `LONGBLOB` - Binário extremamente longo

### Especiais
- `JSON` - Dados JSON
- `BOOLEAN` ou `TINYINT(1)` - Valor booleano (0 ou 1)

## Modificadores de Tipo
- `AUTO_INCREMENT` - Incremento automático
- `UNSIGNED` - Apenas valores positivos
- `ZEROFILL` - Preenche com zeros à esquerda
- `BINARY` - Comparação sensível a maiúsculas/minúsculas

## Opções de ON DELETE/UPDATE

### ON DELETE
- `CASCADE` - Exclui registros relacionados automaticamente
- `SET NULL` - Define como NULL os registros relacionados
- `RESTRICT` - Impede a exclusão se houver registros relacionados
- `NO ACTION` - Similar ao RESTRICT (padrão)
- `SET DEFAULT` - Define o valor padrão para os registros relacionados

### ON UPDATE
- `CASCADE` - Atualiza registros relacionados automaticamente
- `SET NULL` - Define como NULL os registros relacionados
- `RESTRICT` - Impede a atualização se houver registros relacionados
- `NO ACTION` - Similar ao RESTRICT (padrão)
- `SET DEFAULT` - Define o valor padrão para os registros relacionados

## Dicas de Uso

### Boas Práticas para Colunas
1. Use `INT AUTO_INCREMENT` para chaves primárias
2. Prefira `TIMESTAMP` para campos de auditoria:
   ```yaml
   created_at:
     type: TIMESTAMP
     nullable: false
     default: CURRENT_TIMESTAMP
   
   updated_at:
     type: TIMESTAMP
     nullable: false
     default: CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
   ```

3. Para campos de status, use `ENUM`:
   ```yaml
   status:
     type: 'ENUM("ativo", "inativo", "pendente")'
     nullable: false
     default: '"ativo"'
   ```

### Boas Práticas para Chaves Estrangeiras
1. Use sempre o mesmo tipo da chave primária referenciada
2. Para relacionamentos pai-filho, use `ON DELETE CASCADE`:
   ```yaml
   foreign_keys:
     - columns: [user_id]
       reference_table: users
       reference_columns: [id]
       on_delete: CASCADE
       on_update: CASCADE
   ```

3. Para relacionamentos opcionais, use `ON DELETE SET NULL`:
   ```yaml
   foreign_keys:
     - columns: [manager_id]
       reference_table: users
       reference_columns: [id]
       on_delete: SET NULL
       on_update: CASCADE
   ```

### Variáveis de Ambiente
Configure as variáveis de ambiente para credenciais:
```bash
export MYSQL_HOST=localhost
export MYSQL_USER=seu_usuario
export MYSQL_PASSWORD=sua_senha
export MYSQL_DATABASE=seu_banco
```

### Comandos Úteis
```bash
# Gerar modelo de exemplo
python aquaformmy.py model -o meu_modelo.yaml

# Inicializar estado
python aquaformmy.py init

# Verificar mudanças
python aquaformmy.py plan -c meu_modelo.yaml

# Aplicar mudanças
python aquaformmy.py apply -c meu_modelo.yaml

# Destruir recursos
python aquaformmy.py destroy  # Remove tudo
python aquaformmy.py destroy -r users_table  # Remove tabela específica
``` 