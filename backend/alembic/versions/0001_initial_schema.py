"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-07 03:06:49.545094
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('environments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=32), nullable=False),
    sa.Column('node_count', sa.Integer(), nullable=False),
    sa.Column('road_count', sa.Integer(), nullable=False),
    sa.Column('width', sa.Float(), nullable=False),
    sa.Column('height', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )
    op.create_table('experiments',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('scenario_key', sa.String(length=40), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('algorithms', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('repetitions', sa.Integer(), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=False),
    sa.Column('config', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('aggregates', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('fairness', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_experiments_created_at'), 'experiments', ['created_at'], unique=False)
    op.create_table('nodes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('node_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('zone', sa.String(length=16), nullable=False),
    sa.Column('x', sa.Float(), nullable=False),
    sa.Column('y', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('environment_id', 'node_id')
    )
    op.create_index(op.f('ix_nodes_environment_id'), 'nodes', ['environment_id'], unique=False)
    op.create_table('roads',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('environment_id', sa.Integer(), nullable=False),
    sa.Column('road_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.Integer(), nullable=False),
    sa.Column('destination', sa.Integer(), nullable=False),
    sa.Column('distance', sa.Float(), nullable=False),
    sa.Column('road_class', sa.String(length=16), nullable=False),
    sa.Column('travel_time', sa.Float(), nullable=False),
    sa.Column('energy_cost', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('environment_id', 'road_id')
    )
    op.create_index(op.f('ix_roads_environment_id'), 'roads', ['environment_id'], unique=False)
    op.create_table('simulation_runs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('scenario_key', sa.String(length=40), nullable=False),
    sa.Column('scenario_name', sa.String(length=120), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('algorithm', sa.String(length=16), nullable=False),
    sa.Column('heuristic', sa.String(length=16), nullable=False),
    sa.Column('config', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('fingerprints', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('environment_id', sa.Integer(), nullable=True),
    sa.Column('experiment_id', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('sim_time', sa.Float(), nullable=False),
    sa.Column('summary', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_simulation_runs_experiment_id'), 'simulation_runs', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_simulation_runs_started_at'), 'simulation_runs', ['started_at'], unique=False)
    op.create_table('algorithm_results',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('experiment_id', sa.String(length=32), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=True),
    sa.Column('algorithm', sa.String(length=16), nullable=False),
    sa.Column('repetition', sa.Integer(), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('deliveries_completed', sa.Integer(), nullable=False),
    sa.Column('deliveries_failed', sa.Integer(), nullable=False),
    sa.Column('average_delivery_time', sa.Float(), nullable=True),
    sa.Column('avg_route_cost', sa.Float(), nullable=True),
    sa.Column('nodes_explored', sa.Integer(), nullable=False),
    sa.Column('avg_nodes_explored', sa.Float(), nullable=True),
    sa.Column('avg_planning_ms', sa.Float(), nullable=True),
    sa.Column('energy_consumed_kwh', sa.Float(), nullable=False),
    sa.Column('distance_km', sa.Float(), nullable=False),
    sa.Column('replans', sa.Integer(), nullable=False),
    sa.Column('robot_utilization', sa.Float(), nullable=True),
    sa.Column('wall_time_s', sa.Float(), nullable=False),
    sa.Column('metrics', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('timeseries', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_algorithm_results_experiment_id'), 'algorithm_results', ['experiment_id'], unique=False)
    op.create_table('metrics',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('sim_time', sa.Float(), nullable=False),
    sa.Column('data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_metrics_run_time', 'metrics', ['run_id', 'sim_time'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('order_id', sa.String(length=16), nullable=False),
    sa.Column('source', sa.Integer(), nullable=False),
    sa.Column('destination', sa.Integer(), nullable=False),
    sa.Column('priority', sa.String(length=12), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_time', sa.Float(), nullable=False),
    sa.Column('deadline', sa.Float(), nullable=False),
    sa.Column('assigned_robot', sa.String(length=12), nullable=True),
    sa.Column('assigned_time', sa.Float(), nullable=True),
    sa.Column('picked_up_time', sa.Float(), nullable=True),
    sa.Column('delivered_time', sa.Float(), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_run_id'), 'orders', ['run_id'], unique=False)
    op.create_table('robots',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('robot_id', sa.String(length=12), nullable=False),
    sa.Column('model', sa.String(length=32), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('max_battery_wh', sa.Float(), nullable=False),
    sa.Column('final_battery_pct', sa.Float(), nullable=False),
    sa.Column('orders_completed', sa.Integer(), nullable=False),
    sa.Column('distance_km', sa.Float(), nullable=False),
    sa.Column('energy_wh', sa.Float(), nullable=False),
    sa.Column('utilization', sa.Float(), nullable=False),
    sa.Column('replans', sa.Integer(), nullable=False),
    sa.Column('charge_sessions', sa.Integer(), nullable=False),
    sa.Column('depletions', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_robots_run_id'), 'robots', ['run_id'], unique=False)
    op.create_table('simulation_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('sim_time', sa.Float(), nullable=False),
    sa.Column('category', sa.String(length=24), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('severity', sa.String(length=12), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('robot_id', sa.String(length=12), nullable=True),
    sa.Column('order_id', sa.String(length=16), nullable=True),
    sa.Column('road_id', sa.Integer(), nullable=True),
    sa.Column('node_id', sa.Integer(), nullable=True),
    sa.Column('data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_simulation_events_kind'), 'simulation_events', ['kind'], unique=False)
    op.create_index('ix_simulation_events_run_seq', 'simulation_events', ['run_id', 'seq'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_simulation_events_run_seq', table_name='simulation_events')
    op.drop_index(op.f('ix_simulation_events_kind'), table_name='simulation_events')
    op.drop_table('simulation_events')
    op.drop_index(op.f('ix_robots_run_id'), table_name='robots')
    op.drop_table('robots')
    op.drop_index(op.f('ix_orders_run_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_metrics_run_time', table_name='metrics')
    op.drop_table('metrics')
    op.drop_index(op.f('ix_algorithm_results_experiment_id'), table_name='algorithm_results')
    op.drop_table('algorithm_results')
    op.drop_index(op.f('ix_simulation_runs_started_at'), table_name='simulation_runs')
    op.drop_index(op.f('ix_simulation_runs_experiment_id'), table_name='simulation_runs')
    op.drop_table('simulation_runs')
    op.drop_index(op.f('ix_roads_environment_id'), table_name='roads')
    op.drop_table('roads')
    op.drop_index(op.f('ix_nodes_environment_id'), table_name='nodes')
    op.drop_table('nodes')
    op.drop_index(op.f('ix_experiments_created_at'), table_name='experiments')
    op.drop_table('experiments')
    op.drop_table('environments')
