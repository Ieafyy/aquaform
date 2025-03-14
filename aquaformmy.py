#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Aquaformmy - Gerenciador de infraestrutura para MySQL

Um utilitário inspirado no Terraform para gerenciar tabelas de banco de dados 
MySQL a partir de definições YAML.
"""

import os
import sys
import json
import argparse
import logging
import yaml
import mysql.connector
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
logger = logging.getLogger("aquaformmy")

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
    host: str
    user: str
    password: str
    database: str
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
            host=data['host'],
            user=data['user'],
            password=data['password'],
            database=data['database'],
            columns=columns,
            primary_key=data['primary_key'] if isinstance(data['primary_key'], list) else [data['primary_key']],
            foreign_keys=foreign_keys,
            resource_id=resource_id
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'host': self.host,
            'user': self.user,
            'password': self.password,
            'database': self.database,
            'columns': [col.to_dict() for col in self.columns],
            'primary_key': self.primary_key,
        }
        if self.foreign_keys:
            result['foreign_keys'] = [fk.to_dict() for fk in self.foreign_keys]
        
        return result

class MySQLClient:
    def __init__(self, host: str, user: str, password: str, database: str):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
    
    def connect(self) -> bool:
        """Estabelece conexão com o banco de dados MySQL"""
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            return True
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao conectar ao MySQL: {e}{Style.RESET_ALL}")
            return False
    
    def close(self):
        """Fecha a conexão com o banco de dados"""
        if self.connection:
            self.connection.close()
    
    def table_exists(self, table_name: str) -> bool:
        """Verifica se uma tabela existe no banco de dados"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            result = cursor.fetchone()
            cursor.close()
            return result is not None
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Não foi possível verificar a existência da tabela: {e}{Style.RESET_ALL}")
            return False
    
    def create_table(self, table: Table) -> bool:
        """Cria uma nova tabela no banco de dados"""
        try:
            sql = self._generate_create_table_sql(table)
            cursor = self.connection.cursor()
            cursor.execute(sql)
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao criar tabela {table.name}: {e}{Style.RESET_ALL}")
            return False
    
    def alter_table(self, table: Table, changes: Dict[str, Any]) -> bool:
        """Altera uma tabela existente no banco de dados"""
        try:
            cursor = self.connection.cursor()
            success = True
            
            # Adicionar colunas
            for col in changes.get('add_columns', []):
                sql = f'ALTER TABLE `{table.name}` ADD COLUMN `{col.name}` {col.type}'
                if not col.nullable:
                    sql += ' NOT NULL'
                if col.default is not None:
                    sql += f" DEFAULT {col.default}"
                cursor.execute(sql)
            
            # Modificar colunas
            for old_col, new_col in changes.get('modify_columns', []):
                sql = f'ALTER TABLE `{table.name}` MODIFY COLUMN `{new_col.name}` {new_col.type}'
                if not new_col.nullable:
                    sql += ' NOT NULL'
                if new_col.default is not None:
                    sql += f" DEFAULT {new_col.default}"
                cursor.execute(sql)
            
            # Remover colunas
            for col in changes.get('remove_columns', []):
                sql = f'ALTER TABLE `{table.name}` DROP COLUMN `{col.name}`'
                cursor.execute(sql)
            
            # Modificar chaves primárias
            if 'modify_primary_key' in changes:
                old_pk, new_pk = changes['modify_primary_key']
                # Remover chave primária antiga
                cursor.execute(f'ALTER TABLE `{table.name}` DROP PRIMARY KEY')
                
                # Adicionar nova chave primária
                pk_columns = '`, `'.join(new_pk)
                cursor.execute(f'ALTER TABLE `{table.name}` ADD PRIMARY KEY (`{pk_columns}`)')
            
            # Adicionar chaves estrangeiras
            for fk in changes.get('add_foreign_keys', []):
                sql = self._generate_add_foreign_key_sql(table.name, fk)
                cursor.execute(sql)
            
            # Remover chaves estrangeiras
            for fk in changes.get('remove_foreign_keys', []):
                constraint_name = f"{table.name}_{fk.columns[0]}_fkey"  # Simplificação
                cursor.execute(f'ALTER TABLE `{table.name}` DROP FOREIGN KEY `{constraint_name}`')
            
            self.connection.commit()
            cursor.close()
            return success
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao alterar tabela {table.name}: {e}{Style.RESET_ALL}")
            return False
    
    def drop_table(self, table_name: str) -> bool:
        """Remove uma tabela do banco de dados"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(f'DROP TABLE IF EXISTS `{table_name}`')
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao remover tabela {table_name}: {e}{Style.RESET_ALL}")
            return False
    
    def _generate_create_table_sql(self, table: Table) -> str:
        """Gera o SQL para criar uma tabela"""
        columns_sql = []
        
        for col in table.columns:
            col_sql = f'`{col.name}` {col.type}'
            if not col.nullable:
                col_sql += ' NOT NULL'
            if col.default is not None:
                col_sql += f" DEFAULT {col.default}"
            columns_sql.append(col_sql)
        
        # Adiciona chave primária
        pk_columns = '`, `'.join(table.primary_key)
        columns_sql.append(f'PRIMARY KEY (`{pk_columns}`)')
        
        # Adiciona chaves estrangeiras
        if table.foreign_keys:
            for fk in table.foreign_keys:
                fk_columns = '`, `'.join(fk.columns)
                ref_columns = '`, `'.join(fk.reference_columns)
                fk_sql = f'FOREIGN KEY (`{fk_columns}`) REFERENCES `{fk.reference_table}` (`{ref_columns}`)'
                if fk.on_delete != "NO ACTION":
                    fk_sql += f" ON DELETE {fk.on_delete}"
                if fk.on_update != "NO ACTION":
                    fk_sql += f" ON UPDATE {fk.on_update}"
                columns_sql.append(fk_sql)
        
        # Monta a query final
        table_sql = f'CREATE TABLE IF NOT EXISTS `{table.name}` (\n  '
        table_sql += ',\n  '.join(columns_sql)
        table_sql += '\n)'
        
        return table_sql
    
    def _generate_add_foreign_key_sql(self, table_name: str, fk: ForeignKey) -> str:
        """Gera o SQL para adicionar uma chave estrangeira"""
        fk_columns = '`, `'.join(fk.columns)
        ref_columns = '`, `'.join(fk.reference_columns)
        constraint_name = f"{table_name}_{fk.columns[0]}_fkey"  # Simplificação
        
        sql = f'ALTER TABLE `{table_name}` ADD CONSTRAINT `{constraint_name}` '
        sql += f'FOREIGN KEY (`{fk_columns}`) REFERENCES `{fk.reference_table}` (`{ref_columns}`)'
        
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


class Aquaformmy:
    def __init__(self, config_file: Optional[str] = None, state_file: str = 'aquamy.state.json'):
        self.config_file = config_file
        self.state = AquaformState(state_file)
        self.tables = {}
        
        # Carregar configurações
        if config_file:
            self._load_config(config_file)
        else:
            # Carrega todos os arquivos aquamy.*.yaml
            for file_path in glob('aquamy.*.yaml'):
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
                    if resource.get('type') == 'mysql_table':
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
        graph = {table.name: [] for table in self.tables.values()}
        
        for table in self.tables.values():
            if table.name not in graph:
                graph[table.name] = []
        
        for table in self.tables.values():
            if table.foreign_keys:
                for fk in table.foreign_keys:
                    if fk.reference_table in graph:
                        graph[table.name].append(fk.reference_table)
        
        return graph
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """Ordenação topológica do grafo de dependências usando DFS"""
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(node):
            if node in visited:
                return
            if node in temp_visited:
                logger.warning(f"{Fore.YELLOW}[AVISO] Ciclo de dependências detectado envolvendo a tabela {node}{Style.RESET_ALL}")
                return
            
            temp_visited.add(node)
            for neighbor in graph.get(node, []):
                visit(neighbor)
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
        
        for node in list(graph.keys()):
            if node not in visited:
                visit(node)
        
        return result
    
    def _get_table_by_name(self, name: str) -> Optional[Tuple[str, Table]]:
        """Obtém uma tabela pelo nome"""
        for resource_id, table in self.tables.items():
            if table.name == name:
                return resource_id, table
        return None
    
    def _compare_tables(self, old_table: Table, new_table: Table) -> Dict[str, Any]:
        """Compara duas tabelas e retorna as diferenças"""
        changes = {}
        
        # Mapear colunas por nome
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

    def plan(self) -> Dict[str, Any]:
        """Calcula as mudanças necessárias em cada tabela"""
        changes = {}
        
        logger.info(f"{Fore.BLUE}[INFO] Analisando mudanças no MySQL...{Style.RESET_ALL}")
        
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
        
        # Ordenar tabelas conforme dependências
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
        
        # 1. Primeiro atualizações
        for table_name in table_order:
            if table_name in update_actions:
                resource_id, change_data = update_actions[table_name]
                table = change_data['table']
                table_changes = change_data['changes']
                
                client = MySQLClient(
                    host=table.host,
                    user=table.user,
                    password=table.password,
                    database=table.database
                )
                
                if not client.connect():
                    continue
                
                logger.info(f"{Fore.YELLOW}[APPLY] Atualizando tabela {table.name}{Style.RESET_ALL}")
                if client.alter_table(table, table_changes):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela atualizada com sucesso!{Style.RESET_ALL}")
                    self.state.add_resource(resource_id, table.to_dict())
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao atualizar tabela!{Style.RESET_ALL}")
                
                client.close()
        
        # 2. Depois criações
        for table_name in table_order:
            if table_name in create_actions:
                resource_id, change_data = create_actions[table_name]
                table = change_data['table']
                
                client = MySQLClient(
                    host=table.host,
                    user=table.user,
                    password=table.password,
                    database=table.database
                )
                
                if not client.connect():
                    continue
                
                logger.info(f"{Fore.GREEN}[APPLY] Criando tabela {table.name}{Style.RESET_ALL}")
                if client.create_table(table):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela criada com sucesso!{Style.RESET_ALL}")
                    self.state.add_resource(resource_id, table.to_dict())
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao criar tabela!{Style.RESET_ALL}")
                
                client.close()
        
        # 3. Por último as exclusões
        for table_name in reversed(table_order):
            if table_name in delete_actions:
                resource_id, change_data = delete_actions[table_name]
                current_state = self.state.get_resource(resource_id)
                
                client = MySQLClient(
                    host=current_state['host'],
                    user=current_state['user'],
                    password=current_state['password'],
                    database=current_state['database']
                )
                
                if not client.connect():
                    continue
                
                logger.info(f"{Fore.RED}[APPLY] Removendo tabela {table_name}{Style.RESET_ALL}")
                if client.drop_table(table_name):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                    self.state.remove_resource(resource_id)
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
                
                client.close()
        
        # Salvar o estado atualizado
        self.state.save_state()
        logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")
    
    def destroy(self, resource_id: Optional[str] = None):
        """Remove um ou todos os recursos do MySQL"""
        if resource_id:
            # Remover apenas um recurso
            current_state = self.state.get_resource(resource_id)
            if not current_state:
                logger.error(f"{Fore.RED}[ERRO] Recurso não encontrado: {resource_id}{Style.RESET_ALL}")
                return
            
            table_name = current_state.get('name', resource_id)
            client = MySQLClient(
                host=current_state['host'],
                user=current_state['user'],
                password=current_state['password'],
                database=current_state['database']
            )
            
            if not client.connect():
                return
            
            logger.info(f"{Fore.RED}[DESTROY] Removendo tabela {table_name}{Style.RESET_ALL}")
            if client.drop_table(table_name):
                logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                self.state.remove_resource(resource_id)
                self.state.save_state()
                logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")
            else:
                logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
            
            client.close()
        else:
            # Remover todos os recursos
            dependency_graph = self._build_dependency_graph()
            table_order = self._topological_sort(dependency_graph)
            
            # Na exclusão, queremos remover primeiro as tabelas que dependem de outras
            table_order = list(reversed(table_order))
            
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
                
                client = MySQLClient(
                    host=state_data['host'],
                    user=state_data['user'],
                    password=state_data['password'],
                    database=state_data['database']
                )
                
                if not client.connect():
                    continue
                
                logger.info(f"{Fore.RED}[DESTROY] Removendo tabela {table_name}{Style.RESET_ALL}")
                if client.drop_table(table_name):
                    logger.info(f"{Fore.GREEN}  ✓ Tabela removida com sucesso!{Style.RESET_ALL}")
                    self.state.remove_resource(resource_id)
                else:
                    logger.error(f"{Fore.RED}  ✗ Falha ao remover tabela!{Style.RESET_ALL}")
                
                client.close()
            
            # Salvar o estado atualizado
            self.state.save_state()
            logger.info(f"{Fore.BLUE}[INFO] Estado atualizado em {self.state.state_file}{Style.RESET_ALL}")

    def model(self, output_file: str = 'aquamy.model.yaml'):
        """Gera um arquivo YAML de modelo com exemplos de tabelas"""
        model = {
            'resources': {
                'users_table': {
                    'type': 'mysql_table',
                    'name': 'users',
                    'host': '${MYSQL_HOST}',  # Usando variáveis de ambiente como exemplo
                    'user': '${MYSQL_USER}',
                    'password': '${MYSQL_PASSWORD}',
                    'database': '${MYSQL_DATABASE}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'INT AUTO_INCREMENT',
                            'nullable': False
                        },
                        {
                            'name': 'username',
                            'type': 'VARCHAR(100)',
                            'nullable': False
                        },
                        {
                            'name': 'email',
                            'type': 'VARCHAR(255)',
                            'nullable': False,
                            'default': None
                        },
                        {
                            'name': 'password_hash',
                            'type': 'CHAR(60)',  # Para bcrypt hash
                            'nullable': False
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMP',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        },
                        {
                            'name': 'updated_at',
                            'type': 'TIMESTAMP',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
                        }
                    ],
                    'primary_key': ['id']
                },
                'posts_table': {
                    'type': 'mysql_table',
                    'name': 'posts',
                    'host': '${MYSQL_HOST}',
                    'user': '${MYSQL_USER}',
                    'password': '${MYSQL_PASSWORD}',
                    'database': '${MYSQL_DATABASE}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'INT AUTO_INCREMENT',
                            'nullable': False
                        },
                        {
                            'name': 'user_id',
                            'type': 'INT',
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
                            'type': 'ENUM("draft", "published", "archived")',
                            'nullable': False,
                            'default': '"draft"'
                        },
                        {
                            'name': 'views_count',
                            'type': 'INT UNSIGNED',
                            'nullable': False,
                            'default': '0'
                        },
                        {
                            'name': 'published_at',
                            'type': 'DATETIME',
                            'nullable': True
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMP',
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
                'tags_table': {
                    'type': 'mysql_table',
                    'name': 'tags',
                    'host': '${MYSQL_HOST}',
                    'user': '${MYSQL_USER}',
                    'password': '${MYSQL_PASSWORD}',
                    'database': '${MYSQL_DATABASE}',
                    'columns': [
                        {
                            'name': 'id',
                            'type': 'INT AUTO_INCREMENT',
                            'nullable': False
                        },
                        {
                            'name': 'name',
                            'type': 'VARCHAR(50)',
                            'nullable': False
                        },
                        {
                            'name': 'slug',
                            'type': 'VARCHAR(50)',
                            'nullable': False
                        }
                    ],
                    'primary_key': ['id']
                },
                'post_tags_table': {
                    'type': 'mysql_table',
                    'name': 'post_tags',
                    'host': '${MYSQL_HOST}',
                    'user': '${MYSQL_USER}',
                    'password': '${MYSQL_PASSWORD}',
                    'database': '${MYSQL_DATABASE}',
                    'columns': [
                        {
                            'name': 'post_id',
                            'type': 'INT',
                            'nullable': False
                        },
                        {
                            'name': 'tag_id',
                            'type': 'INT',
                            'nullable': False
                        },
                        {
                            'name': 'created_at',
                            'type': 'TIMESTAMP',
                            'nullable': False,
                            'default': 'CURRENT_TIMESTAMP'
                        }
                    ],
                    'primary_key': ['post_id', 'tag_id'],
                    'foreign_keys': [
                        {
                            'columns': ['post_id'],
                            'reference_table': 'posts',
                            'reference_columns': ['id'],
                            'on_delete': 'CASCADE',
                            'on_update': 'CASCADE'
                        },
                        {
                            'columns': ['tag_id'],
                            'reference_table': 'tags',
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
            logger.info("   - MYSQL_HOST: endereço do servidor MySQL")
            logger.info("   - MYSQL_USER: usuário do MySQL")
            logger.info("   - MYSQL_PASSWORD: senha do usuário")
            logger.info("   - MYSQL_DATABASE: nome do banco de dados")
            logger.info("\n2. Personalize o arquivo gerado conforme necessário")
            logger.info("\n3. Execute os comandos do Aquaformmy:")
            logger.info("   python aquaformmy.py init")
            logger.info("   python aquaformmy.py plan")
            logger.info("   python aquaformmy.py apply")
        except Exception as e:
            logger.error(f"{Fore.RED}[ERRO] Falha ao gerar arquivo de modelo: {e}{Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(description='Aquaformmy - Gerenciador de infraestrutura para MySQL')
    
    # Comandos principais
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponíveis')
    
    # Comando init
    init_parser = subparsers.add_parser('init', help='Inicializa o arquivo de estado')
    
    # Comando plan
    plan_parser = subparsers.add_parser('plan', help='Mostra o plano de mudanças sem aplicá-las')
    
    # Comando apply
    apply_parser = subparsers.add_parser('apply', help='Aplica as mudanças ao MySQL')
    
    # Comando destroy
    destroy_parser = subparsers.add_parser('destroy', help='Remove recursos do MySQL')
    destroy_parser.add_argument('-r', '--resource', help='ID do recurso específico a ser removido', required=False)
    
    # Comando model
    model_parser = subparsers.add_parser('model', help='Gera um arquivo YAML de modelo')
    model_parser.add_argument('-o', '--output', help='Nome do arquivo de saída', default='aquamy.model.yaml')
    
    # Opções globais
    for p in [init_parser, plan_parser, apply_parser, destroy_parser, model_parser]:
        p.add_argument('-c', '--config', help='Arquivo de configuração YAML', required=False)
        p.add_argument('-s', '--state', help='Arquivo de estado JSON', default='aquamy.state.json')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    aquaformmy = Aquaformmy(args.config, args.state)
    
    if args.command == 'init':
        aquaformmy.init()
    elif args.command == 'plan':
        aquaformmy.plan()
    elif args.command == 'apply':
        aquaformmy.apply()
    elif args.command == 'destroy':
        aquaformmy.destroy(args.resource)
    elif args.command == 'model':
        aquaformmy.model(args.output)


if __name__ == '__main__':
    main()
