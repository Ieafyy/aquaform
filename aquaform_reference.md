# Referência do Aquaform (Supabase)

## Comandos Disponíveis

### Init
```bash
python aquaform.py init
```
Inicializa o arquivo de estado do Aquaform.

### Plan
```bash
python aquaform.py plan -c config.yaml
```
Mostra as mudanças que serão aplicadas sem executá-las.

### Apply
```bash
python aquaform.py apply -c config.yaml
```
Aplica as mudanças ao banco de dados Supabase.

### Destroy
```bash
# Remove todos os recursos
python aquaform.py destroy

# Remove um recurso específico
python aquaform.py destroy -r users_table
```
Remove recursos do Supabase.

### Model
```bash
# Gera modelo com nome padrão (aqua.model.yaml)
python aquaform.py model

# Especifica um nome de arquivo personalizado
python aquaform.py model -o meu_modelo.yaml
```
Gera um arquivo YAML de exemplo com uma estrutura completa de tabelas relacionadas, incluindo:
- Tabela de usuários com UUID e campos de auditoria
- Tabela de posts com metadados em JSONB e array de tags
- Tabela de comentários com múltiplas chaves estrangeiras

## Tipos de Dados (type)

### Numéricos
- `INTEGER` ou `INT` - Número inteiro de 4 bytes (-2147483648 a +2147483647)
- `BIGINT` - Número inteiro de 8 bytes (-9223372036854775808 a +9223372036854775807)
- `SMALLINT` - Número inteiro de 2 bytes (-32768 a +32767)
- `DECIMAL(p,s)` ou `NUMERIC(p,s)` - Número decimal exato com p dígitos e s casas decimais
- `REAL` - Número de ponto flutuante de 4 bytes (6 dígitos decimais de precisão)
- `DOUBLE PRECISION` - Número de ponto flutuante de 8 bytes (15 dígitos decimais de precisão)
- `SERIAL` - Inteiro com auto-incremento
- `BIGSERIAL` - Inteiro grande com auto-incremento

### Texto
- `CHARACTER(n)` ou `CHAR(n)` - Texto de tamanho fixo
- `CHARACTER VARYING(n)` ou `VARCHAR(n)` - Texto de tamanho variável
- `TEXT` - Texto de tamanho ilimitado
- `UUID` - Identificador único universal

### Data e Hora
- `DATE` - Data (YYYY-MM-DD)
- `TIME` - Hora (HH:MM:SS)
- `TIMESTAMP` - Data e hora (YYYY-MM-DD HH:MM:SS)
- `TIMESTAMPTZ` - Data e hora com fuso horário
- `INTERVAL` - Intervalo de tempo

### Booleano
- `BOOLEAN` - true/false

### Arrays
- `INTEGER[]` - Array de inteiros
- `TEXT[]` - Array de texto
- `VARCHAR[]` - Array de strings
- Qualquer tipo pode ser um array usando `[]`

### JSON
- `JSON` - Dados JSON com validação de sintaxe
- `JSONB` - Dados JSON binário (mais eficiente para consultas)

### Outros
- `BYTEA` - Dados binários ("array de bytes")
- `MONEY` - Quantidade monetária
- `CIDR` - Endereço IPv4 ou IPv6
- `INET` - Endereço IPv4 ou IPv6
- `MACADDR` - Endereço MAC

## Opções de ON DELETE/UPDATE

### ON DELETE
- `CASCADE` - Exclui registros relacionados automaticamente
- `SET NULL` - Define como NULL os registros relacionados
- `RESTRICT` - Impede a exclusão se houver registros relacionados
- `NO ACTION` - Similar ao RESTRICT (padrão)

### ON UPDATE
- `CASCADE` - Atualiza registros relacionados automaticamente
- `SET NULL` - Define como NULL os registros relacionados
- `RESTRICT` - Impede a atualização se houver registros relacionados
- `NO ACTION` - Similar ao RESTRICT (padrão)

## Dicas de Uso

### Boas Práticas para Colunas
1. Use `UUID` para chaves primárias:
   ```yaml
   id:
     type: UUID
     nullable: false
     default: "gen_random_uuid()"
   ```

2. Para campos de auditoria, use `TIMESTAMPTZ`:
   ```yaml
   created_at:
     type: TIMESTAMPTZ
     nullable: false
     default: "CURRENT_TIMESTAMP"
   
   updated_at:
     type: TIMESTAMPTZ
     nullable: false
     default: "CURRENT_TIMESTAMP"
   ```

3. Para arrays e JSON:
   ```yaml
   tags:
     type: VARCHAR[]
     nullable: true
   
   metadata:
     type: JSONB
     nullable: true
   ```

### Boas Práticas para Chaves Estrangeiras
1. Use sempre o mesmo tipo da chave primária referenciada
2. Para relacionamentos pai-filho:
   ```yaml
   foreign_keys:
     - columns: [user_id]
       reference_table: users
       reference_columns: [id]
       on_delete: CASCADE
       on_update: CASCADE
   ```

3. Para relacionamentos opcionais:
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
export SUPABASE_URL=sua_url_supabase
export SUPABASE_KEY=sua_chave_supabase
```

### Exemplo de Configuração Completa
```yaml
resources:
  users_table:
    type: supabase_table
    name: users
    url: ${SUPABASE_URL}
    key: ${SUPABASE_KEY}
    columns:
      - name: id
        type: UUID
        nullable: false
        default: "gen_random_uuid()"
      - name: email
        type: VARCHAR(255)
        nullable: false
      - name: created_at
        type: TIMESTAMPTZ
        nullable: false
        default: "CURRENT_TIMESTAMP"
    primary_key: [id]

  posts_table:
    type: supabase_table
    name: posts
    url: ${SUPABASE_URL}
    key: ${SUPABASE_KEY}
    columns:
      - name: id
        type: UUID
        nullable: false
        default: "gen_random_uuid()"
      - name: user_id
        type: UUID
        nullable: false
      - name: title
        type: VARCHAR(200)
        nullable: false
      - name: content
        type: TEXT
        nullable: true
      - name: metadata
        type: JSONB
        nullable: true
      - name: tags
        type: VARCHAR[]
        nullable: true
    primary_key: [id]
    foreign_keys:
      - columns: [user_id]
        reference_table: users
        reference_columns: [id]
        on_delete: CASCADE
        on_update: CASCADE
```

### Recursos Adicionais
- [Documentação do PostgreSQL](https://www.postgresql.org/docs/current/datatype.html)
- [Documentação do Supabase](https://supabase.com/docs)
- [Tipos de Dados PostgreSQL](https://www.postgresql.org/docs/current/datatype.html)
- [Constraints no PostgreSQL](https://www.postgresql.org/docs/current/ddl-constraints.html) 