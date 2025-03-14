#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Aquaform - Gerenciador de infraestrutura para Supabase

Um utilitário inspirado no Terraform para gerenciar tabelas de banco de dados 
no Supabase a partir de definições YAML.
"""

import os
import sys
import json
import argparse
import logging
import yaml
import requests
import colorama
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from colorama import Fore, Style
from datetime import datetime
from glob import glob

# Inicialização do colorama para saída colorida
colorama.init()

# Configuração do logger
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
)
logger = logging.getLogger("aquaform")

# Classes para modelagem dos dados
@dataclass
class Column:
    name: str
    type: str
    nullable: bool
    default: Optional[Any] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Column':
        return cls(
            name=data['name'],
            type=data['type'],
            nullable=data['nullable'],
            default=data.get('default')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'type': self.type,
            'nullable': self.nullable
        }
        if self.default is not None:
            result['default'] = self.default
        return result
    
    def equals(self, other: 'Column') -> bool:
        """Verifica se duas colunas são idênticas"""
        if self.name != other.name:
            return False
        if self.type != other.type:
            return False
        if self.nullable != other.nullable:
            return False
        if self.default != other.default:
            return False
        return True

@dataclass
class ForeignKey:
    columns: List[str]
    reference_table: str
    reference_columns: List[str]
    on_delete: str = "NO ACTION"
    on_update: str = "NO ACTION"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ForeignKey':
        return cls(
            columns=data['columns'] if isinstance(data['columns'], list) else [data['columns']],
            reference_table=data['reference_table'],
            reference_columns=data['reference_columns'] if isinstance(data['reference_columns'], list) else [data['reference_columns']],
            on_delete=data.get('on_delete', "NO ACTION"),
            on_update=data.get('on_update', "NO ACTION")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'columns': self.columns,
            'reference_table': self.reference_table,
            'reference_columns': self.reference_columns,
            'on_delete': self.on_delete,
            'on_update': self.on_update
        }
    
    def equals(self, other: 'ForeignKey') -> bool:
        """Verifica se duas chaves estrangeiras são idênticas"""
        if self.columns != other.columns:
            return False
        if self.reference_table != other.reference_table:
            return False
        if self.reference_columns != other.reference_columns:
            return False
        if self.on_delete != other.on_delete:
            return False
        if self.on_update != other.on_update:
            return False
        return True

@dataclass
class Table:
    name: str
    url: str
    key: str
    columns: List[Column]
    primary_key: List[str]
    foreign_keys: List[ForeignKey] = None
    resource_id: str = None
    
    @classmethod
    def from_dict(cls, resource_id: str, data: Dict[str, Any]) -> 'Table':
        columns = [Column.from_dict(col) for col in data['columns']]
        foreign_keys = None
        if 'foreign_keys' in data:
            foreign_keys = [ForeignKey.from_dict(fk) for fk in data['foreign_keys']]
        
        return cls(
            name=data['name'],
            url=data['url'],
            key=data['key'],
            columns=columns,
            primary_key=data['primary_key'] if isinstance(data['primary_key'], list) else [data['primary_key']],
            foreign_keys=foreign_keys,
            resource_id=resource_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'url': self.url,
            'key': self.key,
            'columns': [col.to_dict() for col in self.columns],
            'primary_key': self.primary_key,
        }
        if self.foreign_keys:
            result['foreign_keys'] = [fk.to_dict() for fk in self.foreign_keys]
        
        return result


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.rest_url = f"{url}/rest/v1"
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
    
    def table_exists(self, table_name: str) -> bool:
        """Verifica se uma tabela existe no Supabase"""
        try:
            response = requests.get(
                f"{self.url}/rest/v1/",
                headers=self.headers
            )
            response.raise_for_status()
            return table_name in response.json()
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Não foi possível verificar a existência da tabela: {e}{Style.RESET_ALL}")
            return False
    
    def create_table(self, table: Table) -> bool:
        """Cria uma nova tabela no Supabase"""
        try:
            sql = self._generate_create_table_sql(table)
            return self._execute_sql(sql)
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao criar tabela {table.name}: {e}{Style.RESET_ALL}")
            return False

    def alter_table(self, table: Table, changes: Dict[str, Any]) -> bool:
        """Altera uma tabela existente no Supabase"""
        try:
            # Implementar lógica para alterações de tabela
            success = True
            
            # Adicionar colunas
            for col in changes.get('add_columns', []):
                sql = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type}'
                if not col.nullable:
                    sql += ' NOT NULL'
                if col.default is not None:
                    sql += f" DEFAULT {col.default}"
                success = success and self._execute_sql(sql)
            
            # Modificar colunas
            for old_col, new_col in changes.get('modify_columns', []):
                # Alterar tipo
                if old_col.type != new_col.type:
                    sql = f'ALTER TABLE "{table.name}" ALTER COLUMN "{new_col.name}" TYPE {new_col.type}'
                    success = success and self._execute_sql(sql)
                
                # Alterar nullable
                if old_col.nullable != new_col.nullable:
                    if new_col.nullable:
                        sql = f'ALTER TABLE "{table.name}" ALTER COLUMN "{new_col.name}" DROP NOT NULL'
                    else:
                        sql = f'ALTER TABLE "{table.name}" ALTER COLUMN "{new_col.name}" SET NOT NULL'
                    success = success and self._execute_sql(sql)
                
                # Alterar default
                if old_col.default != new_col.default:
                    if new_col.default is None:
                        sql = f'ALTER TABLE "{table.name}" ALTER COLUMN "{new_col.name}" DROP DEFAULT'
                    else:
                        sql = f'ALTER TABLE "{table.name}" ALTER COLUMN "{new_col.name}" SET DEFAULT {new_col.default}'
                    success = success and self._execute_sql(sql)
            
            # Remover colunas
            for col in changes.get('remove_columns', []):
                sql = f'ALTER TABLE "{table.name}" DROP COLUMN "{col.name}"'
                success = success and self._execute_sql(sql)
            
            # Modificar chaves primárias
            if 'modify_primary_key' in changes:
                old_pk, new_pk = changes['modify_primary_key']
                # Remover chave primária antiga
                sql = f'ALTER TABLE "{table.name}" DROP CONSTRAINT IF EXISTS "{table.name}_pkey"'
                success = success and self._execute_sql(sql)
                
                # Adicionar nova chave primária
                pk_columns = '", "'.join(new_pk)
                sql = f'ALTER TABLE "{table.name}" ADD PRIMARY KEY ("{pk_columns}")'
                success = success and self._execute_sql(sql)
            
            # Adicionar chaves estrangeiras
            for fk in changes.get('add_foreign_keys', []):
                sql = self._generate_add_foreign_key_sql(table.name, fk)
                success = success and self._execute_sql(sql)
            
            # Remover chaves estrangeiras
            for fk in changes.get('remove_foreign_keys', []):
                constraint_name = f"{table.name}_{fk.columns[0]}_fkey" # Simplificação - pode precisar de ajuste
                sql = f'ALTER TABLE "{table.name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                success = success and self._execute_sql(sql)
            
            return success
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao alterar tabela {table.name}: {e}{Style.RESET_ALL}")
            return False
    
    def drop_table(self, table_name: str) -> bool:
        """Remove uma tabela do Supabase"""
        try:
            sql = f'DROP TABLE IF EXISTS "{table_name}" CASCADE'
            return self._execute_sql(sql)
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao remover tabela {table_name}: {e}{Style.RESET_ALL}")
            return False
    
    def _execute_sql(self, sql: str) -> bool:
        """Executa uma instrução SQL no Supabase"""
        try:
            # Chamando a função personalizada execute_sql no Supabase
            response = requests.post(
                f"{self.rest_url}/rpc/execute_sql",
                headers=self.headers,
                json={"command": sql}
            )
            response.raise_for_status()
            
            # Verificar o resultado da execução
            result = response.json()
            if isinstance(result, dict) and result.get('success') == False:
                error_msg = result.get('error', 'Erro desconhecido')
                logger.error(f"{Fore.RED}[ERRO] Falha na execução SQL: {error_msg}{Style.RESET_ALL}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha na execução SQL: {sql} - {e}{Style.RESET_ALL}")
            return False
    
    def _generate_create_table_sql(self, table: Table) -> str:
        """Gera o SQL para criar uma tabela"""
        columns_sql = []
        
        for col in table.columns:
            col_sql = f'"{col.name}" {col.type}'
            if not col.nullable:
                col_sql += ' NOT NULL'
            if col.default is not None:
                col_sql += f" DEFAULT {col.default}"
            columns_sql.append(col_sql)
        
        # Adiciona chave primária
        pk_columns = '", "'.join(table.primary_key)
        columns_sql.append(f'PRIMARY KEY ("{pk_columns}")')
        
        # Adiciona chaves estrangeiras
        if table.foreign_keys:
            for fk in table.foreign_keys:
                fk_columns = '", "'.join(fk.columns)
                ref_columns = '", "'.join(fk.reference_columns)
                fk_sql = f'FOREIGN KEY ("{fk_columns}") REFERENCES "{fk.reference_table}" ("{ref_columns}")'
                if fk.on_delete != "NO ACTION":
                    fk_sql += f" ON DELETE {fk.on_delete}"
                if fk.on_update != "NO ACTION":
                    fk_sql += f" ON UPDATE {fk.on_update}"
                columns_sql.append(fk_sql)
        
        # Monta a query de criação
        table_sql = f'CREATE TABLE IF NOT EXISTS "{table.name}" (\n  '
        table_sql += ',\n  '.join(columns_sql)
        table_sql += '\n)'
        
        return table_sql
    
    def _generate_add_foreign_key_sql(self, table_name: str, fk: ForeignKey) -> str:
        """Gera o SQL para adicionar uma chave estrangeira"""
        fk_columns = '", "'.join(fk.columns)
        ref_columns = '", "'.join(fk.reference_columns)
        constraint_name = f"{table_name}_{fk.columns[0]}_fkey"  # Simplificação
        
        sql = f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
        sql += f'FOREIGN KEY ("{fk_columns}") REFERENCES "{fk.reference_table}" ("{ref_columns}")'
        
        if fk.on_delete != "NO ACTION":
            sql += f" ON DELETE {fk.on_delete}"
        if fk.on_update != "NO ACTION":
            sql += f" ON UPDATE {fk.on_update}"
            
        return sql


class AquaformState:
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Carrega o estado do arquivo ou retorna um estado vazio se não existir"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as file:
                    return json.load(file)
            except json.JSONDecodeError:
                logger.error(f"{Fore.RED}[ERRO] Arquivo de estado inválido: {self.state_file}{Style.RESET_ALL}")
                return {'resources': {}, 'last_updated': None}
        return {'resources': {}, 'last_updated': None}
    
    def save_state(self):
        """Salva o estado atual no arquivo"""
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as file:
            json.dump(self.state, file, indent=2)
    
    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Obtém um recurso do estado pelo ID"""
        return self.state.get('resources', {}).get(resource_id)
    
    def add_resource(self, resource_id: str, resource: Dict[str, Any]):
        """Adiciona ou atualiza um recurso no estado"""
        if 'resources' not in self.state:
            self.state['resources'] = {}
        self.state['resources'][resource_id] = resource
    
    def remove_resource(self, resource_id: str):
        """Remove um recurso do estado"""
        if 'resources' in self.state and resource_id in self.state['resources']:
            del self.state['resources'][resource_id]


class Aquaform:
    def __init__(self, config_file: Optional[str] = None, state_file: str = 'aqua.state.json', db_type: str = 'supabase'):
        self.config_file = config_file
        self.state = AquaformState(state_file)
        self.db_type = db_type
        self.tables = {}
        
        # Carregar configurações
        if config_file:
            self._load_config(config_file)
        else:
            # Carrega todos os arquivos aqua.*.yaml
            for file_path in glob('aqua.*.yaml'):
                self._load_config(file_path)
    
    def _load_config(self, file_path: str):
        """Carrega as configurações de um arquivo YAML"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                
                if not config or 'resources' not in config:
                    logger.error(f"{Fore.RED}[ERRO] Arquivo de configuração inválido: {file_path}{Style.RESET_ALL}")
                    return
                
                for resource_id, resource in config['resources'].items():
                    if resource.get('type') == 'supabase_table':
                        try:
                            table = Table.from_dict(resource_id, resource)
                            self.tables[resource_id] = table
                        except KeyError as e:
                            logger.error(f"{Fore.RED}[ERRO] Chave obrigatória ausente na tabela {resource_id}: {e}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao carregar arquivo de configuração {file_path}: {e}{Style.RESET_ALL}")
    
    def init(self):
        """Inicializa o estado se não existir"""
        if not os.path.exists(self.state.state_file):
            logger.info(f"{Fore.GREEN}[INFO] Inicializando o arquivo de estado: {self.state.state_file}{Style.RESET_ALL}")
            self.state.save_state()
        else:
            logger.info(f"{Fore.BLUE}[INFO] Estado já existe: {self.state.state_file}{Style.RESET_ALL}")
    
    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        """Constrói um grafo de dependências entre as tabelas com base nas chaves estrangeiras"""
        # Inicializar grafo: tabela -> lista de tabelas das quais depende
        graph = {table.name: [] for table in self.tables.values()}
        
        # Adicionar todas as tabelas ao grafo, mesmo as que não têm dependências
        for table in self.tables.values():
            if table.name not in graph:
                graph[table.name] = []
        
        # Mapear resource_id para nome da tabela
        resource_to_table = {resource_id: table.name for resource_id, table in self.tables.items()}
        
        # Para cada tabela, adicionar suas dependências
        for table in self.tables.values():
            if table.foreign_keys:
                for fk in table.foreign_keys:
                    # A tabela atual depende da tabela referenciada
                    if fk.reference_table in graph:
                        graph[table.name].append(fk.reference_table)
        
        return graph
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """Ordenação topológica do grafo de dependências usando DFS"""
        # Inicializar resultado e conjunto de visitados
        result = []
        visited = set()
        temp_visited = set()  # Para detectar ciclos
        
        def visit(node):
            """Visita um nó e seus vizinhos usando DFS"""
            # Se já visitado permanentemente, retornar
            if node in visited:
                return
            
            # Se já visitado temporariamente, temos um ciclo
            if node in temp_visited:
                logger.warning(f"{Fore.YELLOW}[AVISO] Ciclo de dependências detectado envolvendo a tabela {node}{Style.RESET_ALL}")
                return
            
            # Marcar como visitado temporariamente
            temp_visited.add(node)
            
            # Visitar todos os vizinhos (dependências)
            for neighbor in graph.get(node, []):
                visit(neighbor)
            
            # Marcar como visitado permanentemente e adicionar ao resultado
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
        
        # Visitar todos os nós
        for node in list(graph.keys()):
            if node not in visited:
                visit(node)
        
        # Não precisamos inverter - a ordem já está correta (tabelas sem dependências primeiro)
        return result
    
    def _get_table_by_name(self, name: str) -> Optional[Tuple[str, Table]]:
        """Obtém uma tabela pelo nome"""
        for resource_id, table in self.tables.items():
            if table.name == name:
                return resource_id, table
        return None
    
    def plan(self) -> Dict[str, Any]:
        """Calcula as mudanças necessárias em cada tabela"""
        changes = {}
        
        logger.info(f"{Fore.BLUE}[INFO] Conectando ao Supabase...{Style.RESET_ALL}")
        
        # Construir e mostrar o grafo de dependências
        dependency_graph = self._build_dependency_graph()
        
        # Mostrar informações de dependência
        logger.info(f"{Fore.BLUE}[INFO] Analisando dependências entre tabelas...{Style.RESET_ALL}")
        for table_name, dependencies in dependency_graph.items():
            if dependencies:
                deps_str = ", ".join(dependencies)
                logger.info(f"{Fore.BLUE}[INFO] Tabela {table_name} depende de: {deps_str}{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.BLUE}[INFO] Tabela {table_name} não tem dependências{Style.RESET_ALL}")
        
        # Ordenar tabelas conforme dependências
        table_order = self._topological_sort(dependency_graph)
        logger.info(f"{Fore.BLUE}[INFO] Ordem de criação das tabelas: {', '.join(table_order)}{Style.RESET_ALL}")
        
        for resource_id, table in self.tables.items():
            # Verifica se a tabela já existe no estado
            current_state = self.state.get_resource(resource_id)
            
            if not current_state:
                # Tabela nova, será criada
                changes[resource_id] = {
                    'action': 'create',
                    'table': table
                }
                logger.info(f"{Fore.GREEN}[PLAN] Tabela {table.name}:")
                logger.info(f"{Fore.GREEN}  + Criar tabela nova{Style.RESET_ALL}")
            else:
                # Tabela existente, verificar alterações
                table_changes = self._compare_tables(
                    Table.from_dict(resource_id, current_state),
                    table
                )
                
                if table_changes:
                    changes[resource_id] = {
                        'action': 'update',
                        'table': table,
                        'changes': table_changes
                    }
                    
                    logger.info(f"{Fore.YELLOW}[PLAN] Tabela {table.name}:{Style.RESET_ALL}")
                    
                    # Mostrar colunas adicionadas
                    for col in table_changes.get('add_columns', []):
                        logger.info(f"{Fore.GREEN}  + Adicionar coluna \"{col.name}\" ({col.type}, {'' if not col.nullable else 'NOT '}NULL){Style.RESET_ALL}")
                    
                    # Mostrar colunas modificadas
                    for old_col, new_col in table_changes.get('modify_columns', []):
                        logger.info(f"{Fore.YELLOW}  ~ Modificar coluna \"{new_col.name}\" ({old_col.type} → {new_col.type}){Style.RESET_ALL}")
                    
                    # Mostrar colunas removidas
                    for col in table_changes.get('remove_columns', []):
                        logger.info(f"{Fore.RED}  - Remover coluna \"{col.name}\"{Style.RESET_ALL}")
                    
                    # Mostrar alterações de chave primária
                    if 'modify_primary_key' in table_changes:
                        old_pk, new_pk = table_changes['modify_primary_key']
                        logger.info(f"{Fore.YELLOW}  ~ Modificar chave primária ({', '.join(old_pk)} → {', '.join(new_pk)}){Style.RESET_ALL}")
                    
                    # Mostrar chaves estrangeiras adicionadas
                    for fk in table_changes.get('add_foreign_keys', []):
                        logger.info(f"{Fore.GREEN}  + Adicionar chave estrangeira para {fk.columns} → {fk.reference_table}.{fk.reference_columns}{Style.RESET_ALL}")
                    
                    # Mostrar chaves estrangeiras removidas
                    for fk in table_changes.get('remove_foreign_keys', []):
                        logger.info(f"{Fore.RED}  - Remover chave estrangeira de {fk.columns} → {fk.reference_table}.{fk.reference_columns}{Style.RESET_ALL}")
        
        # Verificar recursos para remover
        for resource_id in list(self.state.state.get('resources', {}).keys()):
            if resource_id not in self.tables:
                current_state = self.state.get_resource(resource_id)
                if current_state:
                    table_name = current_state.get('name', resource_id)
                    changes[resource_id] = {
                        'action': 'delete',
                        'table_name': table_name
                    }
                    logger.info(f"{Fore.RED}[PLAN] Tabela {table_name}:")
                    logger.info(f"{Fore.RED}  - Remover tabela{Style.RESET_ALL}")
        
        if not changes:
            logger.info(f"{Fore.BLUE}[INFO] Nenhuma mudança detectada{Style.RESET_ALL}")
        
        return changes
    
    def apply(self):
        """Aplica as mudanças calculadas por plan()"""
        changes = self.plan()
        
        if not changes:
            logger.info(f"{Fore.BLUE}[INFO] Nenhuma mudança para aplicar{Style.RESET_ALL}")
            return
        
        logger.info(f"{Fore.BLUE}[APPLY] Aplicando mudanças...{Style.RESET_ALL}")
        
        # Construir grafo de dependências
        dependency_graph = self._build_dependency_graph()
        
        # Ordenar tabelas conforme dependências para criar/atualizar na ordem correta
        table_order = self._topological_sort(dependency_graph)
        
        # Agrupar alterações por ação e nome da tabela
        create_actions = {}
        update_actions = {}
        delete_actions = {}
        
        for resource_id, change_data in changes.items():
            action = change_data['action']
            
            if action == 'create':
                table = change_data['table']
                create_actions[table.name] = (resource_id, change_data)
            elif action == 'update':
                table = change_data['table']
                update_actions[table.name] = (resource_id, change_data)
            elif action == 'delete':
                table_name = change_data['table_name']
                delete_actions[table_name] = (resource_id, change_data)
        
        # Processar as ações na ordem correta
        
        # 1. Primeiro atualizações (pois modificar é mais seguro que criar/excluir)
        for table_name in table_order:
            if table_name in update_actions:
                resource_id, change_data = update_actions[table_name]
                table = change_data['table']
                table_changes = change_data['changes']
                url, key = self._resolve_vars(table.url, table.key)
                client = SupabaseClient(url, key)
                
                logger.info(f"{Fore.YELLOW}[APPLY] Atualizando tabela {table.name}{Style.RESET_ALL}")
                if client.alter_table(table, table_changes):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela atualizada com sucesso!{Style.RESET_ALL}")
                    self.state.add_resource(resource_id, table.to_dict())
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao atualizar tabela!{Style.RESET_ALL}")
        
        # 2. Depois criações (na ordem de dependências - primeiro tabelas sem dependências)
        for table_name in table_order:
            if table_name in create_actions:
                resource_id, change_data = create_actions[table_name]
                table = change_data['table']
                url, key = self._resolve_vars(table.url, table.key)
                client = SupabaseClient(url, key)
                
                logger.info(f"{Fore.GREEN}[APPLY] Criando tabela {table.name}{Style.RESET_ALL}")
                if client.create_table(table):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela criada com sucesso!{Style.RESET_ALL}")
                    self.state.add_resource(resource_id, table.to_dict())
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao criar tabela!{Style.RESET_ALL}")
        
        # 3. Por último as exclusões (mantemos a ordem original, começando pelas que têm dependentes)
        for table_name in table_order:
            if table_name in delete_actions:
                resource_id, change_data = delete_actions[table_name]
                current_state = self.state.get_resource(resource_id)
                url, key = self._resolve_vars(current_state['url'], current_state['key'])
                client = SupabaseClient(url, key)
                
                logger.info(f"{Fore.RED}[APPLY] Removendo tabela {table_name}{Style.RESET_ALL}")
                if client.drop_table(table_name):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                    self.state.remove_resource(resource_id)
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
        
        # Salvar o estado atualizado
        self.state.save_state()
        logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")
    
    def destroy(self, resource_id: Optional[str] = None):
        """Remove um ou todos os recursos do Supabase"""
        if resource_id:
            # Remover apenas um recurso
            current_state = self.state.get_resource(resource_id)
            if not current_state:
                logger.error(f"{Fore.RED}[ERRO] Recurso não encontrado: {resource_id}{Style.RESET_ALL}")
                return
            
            table_name = current_state.get('name', resource_id)
            url, key = self._resolve_vars(current_state['url'], current_state['key'])
            client = SupabaseClient(url, key)
            
            logger.info(f"{Fore.RED}[DESTROY] Removendo tabela {table_name}{Style.RESET_ALL}")
            if client.drop_table(table_name):
                logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                self.state.remove_resource(resource_id)
                self.state.save_state()
                logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")
            else:
                logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
        else:
            # Remover todos os recursos
            # Construir grafo de dependências
            dependency_graph = self._build_dependency_graph()
            
            # Ordenar tabelas conforme dependências para excluir na ordem correta
            table_order = self._topological_sort(dependency_graph)
            # Na exclusão, queremos remover primeiro as tabelas que dependem de outras
            # então mantemos a ordem original do topological sort
            
            # Mapear nome da tabela para resource_id
            table_name_to_resource = {}
            for resource_id, table in self.tables.items():
                table_name_to_resource[table.name] = resource_id
            
            # Adicionar tabelas do estado que não estão nos arquivos YAML
            for resource_id, state_data in self.state.state.get('resources', {}).items():
                table_name = state_data.get('name')
                if table_name and table_name not in table_name_to_resource:
                    table_name_to_resource[table_name] = resource_id
            
            if not table_name_to_resource:
                logger.info(f"{Fore.BLUE}[INFO] Nenhum recurso para destruir{Style.RESET_ALL}")
                return
            
            logger.info(f"{Fore.RED}[DESTROY] Removendo todos os recursos na ordem: {', '.join(table_order)}{Style.RESET_ALL}")
            
            for table_name in table_order:
                resource_id = table_name_to_resource.get(table_name)
                if not resource_id:
                    continue
                
                state_data = self.state.get_resource(resource_id)
                if not state_data:
                    continue
                
                url, key = self._resolve_vars(state_data['url'], state_data['key'])
                client = SupabaseClient(url, key)
                
                logger.info(f"{Fore.RED}[DESTROY] Removendo tabela {table_name}{Style.RESET_ALL}")
                if client.drop_table(table_name):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                    self.state.remove_resource(resource_id)
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
            
            # Salvar o estado atualizado
            self.state.save_state()
            logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")
    
    def _compare_tables(self, old_table: Table, new_table: Table) -> Dict[str, Any]:
        """Compara duas tabelas e retorna as diferenças"""
        changes = {}
        
        # Mapear colunas por nome para facilitar a comparação
        old_columns_map = {col.name: col for col in old_table.columns}
        new_columns_map = {col.name: col for col in new_table.columns}
        
        # Verificar colunas adicionadas
        add_columns = []
        for col_name, col in new_columns_map.items():
            if col_name not in old_columns_map:
                add_columns.append(col)
        
        if add_columns:
            changes['add_columns'] = add_columns
        
        # Verificar colunas modificadas
        modify_columns = []
        for col_name, new_col in new_columns_map.items():
            if col_name in old_columns_map and not new_col.equals(old_columns_map[col_name]):
                modify_columns.append((old_columns_map[col_name], new_col))
        
        if modify_columns:
            changes['modify_columns'] = modify_columns
        
        # Verificar colunas removidas
        remove_columns = []
        for col_name, col in old_columns_map.items():
            if col_name not in new_columns_map:
                remove_columns.append(col)
        
        if remove_columns:
            changes['remove_columns'] = remove_columns
        
        # Verificar alteração de chave primária
        if old_table.primary_key != new_table.primary_key:
            changes['modify_primary_key'] = (old_table.primary_key, new_table.primary_key)
        
        # Verificar chaves estrangeiras
        if old_table.foreign_keys or new_table.foreign_keys:
            old_fks = old_table.foreign_keys or []
            new_fks = new_table.foreign_keys or []
            
            # Mapear chaves estrangeiras por coluna para facilitar a comparação
            old_fks_map = {tuple(fk.columns): fk for fk in old_fks}
            new_fks_map = {tuple(fk.columns): fk for fk in new_fks}
            
            # Verificar chaves estrangeiras adicionadas
            add_fks = []
            for cols, fk in new_fks_map.items():
                if cols not in old_fks_map:
                    add_fks.append(fk)
            
            if add_fks:
                changes['add_foreign_keys'] = add_fks
            
            # Verificar chaves estrangeiras modificadas
            # (tratamos como remoção + adição por simplicidade)
            for cols, new_fk in new_fks_map.items():
                if cols in old_fks_map and not new_fk.equals(old_fks_map[cols]):
                    if 'remove_foreign_keys' not in changes:
                        changes['remove_foreign_keys'] = []
                    changes['remove_foreign_keys'].append(old_fks_map[cols])
                    
                    if 'add_foreign_keys' not in changes:
                        changes['add_foreign_keys'] = []
                    changes['add_foreign_keys'].append(new_fk)
            
            # Verificar chaves estrangeiras removidas
            remove_fks = []
            for cols, fk in old_fks_map.items():
                if cols not in new_fks_map:
                    remove_fks.append(fk)
            
            if remove_fks:
                if 'remove_foreign_keys' not in changes:
                    changes['remove_foreign_keys'] = []
                changes['remove_foreign_keys'] += remove_fks
        
        return changes
    
    def _resolve_vars(self, url: str, key: str) -> Tuple[str, str]:
        """Resolve variáveis de ambiente nas configurações"""
        if url.startswith("${") and url.endswith("}"):
            env_var = url[2:-1]
            url = os.environ.get(env_var, url)
        
        if key.startswith("${") and key.endswith("}"):
            env_var = key[2:-1]
            key = os.environ.get(env_var, key)
        
        return url, key

    def model(self, output_file: str = 'aqua.model.yaml'):
        """Gera um arquivo YAML de modelo com exemplos de tabelas"""
        model = {
            'resources': {
                'users_table': {
                    'type': 'supabase_table',
                    'name': 'users',
                    'url': '${SUPABASE_URL}',
                    'key': '${SUPABASE_KEY}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'UUID',
                            'nullable': False,
                            'default': 'gen_random_uuid()'
                        },
                        {
                            'name': 'email',
                            'type': 'VARCHAR(255)',
                            'nullable': False
                        },
                        {
                            'name': 'full_name',
                            'type': 'VARCHAR(100)',
                            'nullable': True
                        },
                        {
                            'name': 'status',
                            'type': 'VARCHAR(20)',
                            'nullable': False,
                            'default': "'active'"
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMPTZ',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        },
                        {
                            'name': 'updated_at',
                            'type': 'TIMESTAMPTZ',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        }
                    ],
                    'primary_key': ['id']
                },
                'posts_table': {
                    'type': 'supabase_table',
                    'name': 'posts',
                    'url': '${SUPABASE_URL}',
                    'key': '${SUPABASE_KEY}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'UUID',
                            'nullable': False,
                            'default': 'gen_random_uuid()'
                        },
                        {
                            'name': 'user_id',
                            'type': 'UUID',
                            'nullable': False
                        },
                        {
                            'name': 'title',
                            'type': 'VARCHAR(200)',
                            'nullable': False
                        },
                        {
                            'name': 'content',
                            'type': 'TEXT',
                            'nullable': True
                        },
                        {
                            'name': 'status',
                            'type': 'VARCHAR(20)',
                            'nullable': False,
                            'default': "'draft'"
                        },
                        {
                            'name': 'metadata',
                            'type': 'JSONB',
                            'nullable': True
                        },
                        {
                            'name': 'tags',
                            'type': 'VARCHAR[]',
                            'nullable': True
                        },
                        {
                            'name': 'published_at',
                            'type': 'TIMESTAMPTZ',
                            'nullable': True
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMPTZ',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        }
                    ],
                    'primary_key': ['id'],
                    'foreign_keys': [
                        {
                            'columns': ['user_id'],
                            'reference_table': 'users',
                            'reference_columns': ['id'],
                            'on_delete': 'CASCADE',
                            'on_update': 'CASCADE'
                        }
                    ]
                },
                'comments_table': {
                    'type': 'supabase_table',
                    'name': 'comments',
                    'url': '${SUPABASE_URL}',
                    'key': '${SUPABASE_KEY}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'UUID',
                            'nullable': False,
                            'default': 'gen_random_uuid()'
                        },
                        {
                            'name': 'post_id',
                            'type': 'UUID',
                            'nullable': False
                        },
                        {
                            'name': 'user_id',
                            'type': 'UUID',
                            'nullable': False
                        },
                        {
                            'name': 'content',
                            'type': 'TEXT',
                            'nullable': False
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMPTZ',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        }
                    ],
                    'primary_key': ['id'],
                    'foreign_keys': [
                        {
                            'columns': ['post_id'],
                            'reference_table': 'posts',
                            'reference_columns': ['id'],
                            'on_delete': 'CASCADE',
                            'on_update': 'CASCADE'
                        },
                        {
                            'columns': ['user_id'],
                            'reference_table': 'users',
                            'reference_columns': ['id'],
                            'on_delete': 'CASCADE',
                            'on_update': 'CASCADE'
                        }
                    ]
                }
            }
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as file:
                yaml.dump(model, file, sort_keys=False, indent=2, allow_unicode=True)
            logger.info(f"{Fore.GREEN}[INFO] Arquivo de modelo gerado com sucesso: {output_file}{Style.RESET_ALL}")
            
            # Adicionar instruções de uso
            logger.info(f"\n{Fore.BLUE}[INFO] Instruções de uso:{Style.RESET_ALL}")
            logger.info("1. Configure as variáveis de ambiente necessárias:")
            logger.info("   - SUPABASE_URL: URL do seu projeto Supabase")
            logger.info("   - SUPABASE_KEY: Chave de acesso do Supabase")
            logger.info("\n2. Personalize o arquivo gerado conforme necessário")
            logger.info("\n3. Execute os comandos do Aquaform:")
            logger.info("   python aquaform.py init")
            logger.info("   python aquaform.py plan")
            logger.info("   python aquaform.py apply")
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao gerar arquivo de modelo: {e}{Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(description='Aquaform - Gerenciador de infraestrutura para Supabase')
    
    # Comandos principais
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponíveis')
    
    # Comando init
    init_parser = subparsers.add_parser('init', help='Inicializa o arquivo de estado')
    
    # Comando plan
    plan_parser = subparsers.add_parser('plan', help='Mostra o plano de mudanças sem aplicá-las')
    
    # Comando apply
    apply_parser = subparsers.add_parser('apply', help='Aplica as mudanças ao Supabase')
    
    # Comando destroy
    destroy_parser = subparsers.add_parser('destroy', help='Remove recursos do Supabase')
    destroy_parser.add_argument('-r', '--resource', help='ID do recurso específico a ser removido', required=False)
    
    # Comando model
    model_parser = subparsers.add_parser('model', help='Gera um arquivo YAML de modelo')
    model_parser.add_argument('-o', '--output', help='Nome do arquivo de saída', default='aqua.model.yaml')
    
    # Opções globais
    for p in [init_parser, plan_parser, apply_parser, destroy_parser, model_parser]:
        p.add_argument('-c', '--config', help='Arquivo de configuração YAML', required=False)
        p.add_argument('-s', '--state', help='Arquivo de estado JSON', default='aqua.state.json')
        p.add_argument('-t', '--type', help='Tipo de banco de dados', default='supabase')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    aquaform = Aquaform(args.config, args.state, args.type)
    
    if args.command == 'init':
        aquaform.init()
    elif args.command == 'plan':
        aquaform.plan()
    elif args.command == 'apply':
        aquaform.apply()
    elif args.command == 'destroy':
        aquaform.destroy(args.resource)
    elif args.command == 'model':
        aquaform.model(args.output)


if __name__ == '__main__':
    main() 