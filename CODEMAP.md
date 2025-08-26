# Code Map

## extracted_repo/app/__init__.py (3 lines)

## extracted_repo/app/adapters/cache_store.py (1 lines)

## extracted_repo/app/adapters/delivery_line.py (221 lines)
- Classes: LineDelivery
- Functions: _env_timeout, _is_dry_run, _get_delivery, reply_message, push_message, broadcast_message

## extracted_repo/app/adapters/line/__init__.py (1 lines)

## extracted_repo/app/adapters/line/client.py (65 lines)
- Functions: _clean_invisible, _validate_token, _auth_headers

## extracted_repo/app/adapters/price_provider.py (143 lines)
- Functions: _normalize_symbol, get_spot_text_ccxt, get_spot_ccxt_safe, get_spot_text_ccxt_safe

## extracted_repo/app/analysis/__init__.py (31 lines)
- Functions: __getattr__

## extracted_repo/app/analysis/dow.py (260 lines)
- Functions: _logic_fingerprint, _coerce_to_df, _pivots, _build_swings, _extract_recent_sequence, _dow_rules_decision, analyze_dow_rules, analyze_dow

## extracted_repo/app/analysis/elliott.py (257 lines)
- Classes: Rule
- Functions: _fractals, _build_swings, _leg_len, _retracement_ratio, _ratio, _dir, _report, _check_impulse_rules, _check_zigzag_rules, _check_flat_rules, _check_triangle_rules, analyze_elliott_rules, analyze_elliott

## extracted_repo/app/analysis/entry_exit.py (307 lines)
- Functions: _fmt, _safe_load_yaml, _extract_wave_label, _extract_dow_label, _atr_pct, suggest_watch_levels, suggest_trade, _mark_val, format_trade_text, format_trade_text_detailed

## extracted_repo/app/analysis/fibonacci.py (151 lines)
- Functions: _detect_direction, _key, fib_levels, fib_extensions, merge_levels, detect_fib_cluster

## extracted_repo/app/analysis/filters.py (321 lines)
- Functions: _to_df, _ema, _atr_pct, _vol_ma_and_ratio, _roc_pct, _atr_pct_series, trend_filter, volatility_filter, session_filter, volume_filter, is_sideway_df, side_confidence, evaluate_filters

## extracted_repo/app/analysis/indicators.py (212 lines)
- Functions: ema, rsi, macd, adx, stoch_kd, volume_metrics, apply_indicators

## extracted_repo/app/analysis/patterns.py (195 lines)
- Functions: _swing_points, _leg_len, _dir, _retracement_ratio, _ratio, detect_elliott_rules, detect_zigzag_rules, detect_flat_rules, detect_triangle_rules, detect_patterns_rules, detect_breakout, detect_inside_bar

## extracted_repo/app/analysis/timeframes.py (441 lines)
- Classes: RequiredColumnsMissing
- Functions: _sheet_name, _normalize, _resolve_sheet_name, _ensure_required_columns, _parse_and_clean_strict, _validate_monotonic, _read_excel_strict, _csv_path, _read_csv_strict, _resample_to_1w, _tf_to_exchange_interval, _fetch_ohlcv_binance, _postprocess_realtime_df, _fetch_from_providers, get_data, _cache_set, get_last_updated, _seconds_until_next_bar, _update_blocking_wrapper

## extracted_repo/app/config/__init__.py (19 lines)

## extracted_repo/app/config/symbols.py (35 lines)
- Functions: is_supported, resolve_symbol

## extracted_repo/app/engine/__init__.py (1 lines)

## extracted_repo/app/engine/signal_engine.py (318 lines)
- Classes: SignalEngine
- Functions: build_signal_payload, build_line_text

## extracted_repo/app/features/alerts/percentage_change.py (90 lines)
- Functions: compute_pct_change, crossed_threshold, should_rearm_after_alert, evaluate_percentage_alert

## extracted_repo/app/features/alerts/price_reach.py (41 lines)
- Functions: add_watch, remove_watch

## extracted_repo/app/features/replies/keyword_reply.py (135 lines)
- Functions: get_reply, parse_price_command, parse_analysis_mock, parse_analyze_command

## extracted_repo/app/logic/__init__.py (5 lines)

## extracted_repo/app/logic/elliott_logic.py (261 lines)
- Functions: _coerce_to_df, _ema, _atr, _call_base_classify, enrich_context, map_kind, blend_with_weekly_context, classify_elliott_with_kind, classify_elliott

## extracted_repo/app/logic/scenarios.py (403 lines)
- Functions: _safe_load_yaml, _merge, _get_profile, _fractals, _recent_swings, _softmax3, _pct, _analyze_dow_safe, _elliott_guess_when_unknown, analyze_scenarios

## extracted_repo/app/logic/strategies.py (140 lines)
- Functions: _rt_momentum_imports, moving_average_cross, rsi_signal, some_strategy_func, momentum_trend, momentum_trend_series

## extracted_repo/app/logic/strategies_momentum.py (366 lines)
- Classes: MomentumConfig
- Functions: _hash_this, _engine_log, _reason, _to_df, _ema, _to_numeric, _rsi, _atr, _decide_bias, momentum_signal_series, momentum_last_signal, momentum_breakout, some_strategy_func

## extracted_repo/app/main.py (173 lines)
- Functions: get_line_push_fn, create_app, index

## extracted_repo/app/routers/__init__.py (7 lines)

## extracted_repo/app/routers/analyze.py (119 lines)
- Functions: _norm_symbol, _norm_tf, analyze_endpoint, analyze_wave_alias

## extracted_repo/app/routers/chat.py (22 lines)
- Classes: ChatMessage

## extracted_repo/app/routers/health.py (9 lines)
- Functions: health

## extracted_repo/app/routers/line.py (102 lines)
- Classes: PushBody, BroadcastBody
- Functions: _env, _client, line_health, line_push, line_broadcast

## extracted_repo/app/routers/line_webhook.py (136 lines)
- Functions: _get_env, _client, _parse_text

## extracted_repo/app/scheduler/runner.py (131 lines)
- Functions: _format_alert_text

## extracted_repo/app/schemas/__init__.py (3 lines)

## extracted_repo/app/schemas/chat_io.py (6 lines)
- Classes: ChatRequest, ChatResponse

## extracted_repo/app/schemas/indicators.py (1 lines)

## extracted_repo/app/schemas/series.py (1 lines)

## extracted_repo/app/schemas/signal.py (28 lines)
- Classes: PositionSchema, SignalResponse

## extracted_repo/app/services/__init__.py (3 lines)

## extracted_repo/app/services/chat_service.py (7 lines)
- Functions: simple_reply

## extracted_repo/app/services/message_templates.py (28 lines)
- Functions: build_price_message

## extracted_repo/app/services/news_service.py (403 lines)
- Classes: NewsItem, BaseSource, RssSource, NewsApiSource, NewsService
- Functions: _text, _strip_html, _normalize_whitespace, _iso_utc, _make_id, _detect_ns, _parse_datetime, _guess_tickers, get_service

## extracted_repo/app/services/notifier_line.py (93 lines)
- Classes: LineClient, LineNotifier
- Functions: get_notifier, send_message

## extracted_repo/app/services/price_provider_binance.py (29 lines)
- Classes: BinancePriceProvider

## extracted_repo/app/services/signal_service.py (107 lines)
- Functions: analyze_and_get_payload, analyze_and_get_text, analyze_batch, fetch_price, fetch_price_text

## extracted_repo/app/services/trade_plan_store.py (157 lines)
- Functions: _init_file, _read_all, _write_all, save_trade_plan, list_trade_plans, mark_closed, mark_target_hit

## extracted_repo/app/services/translator.py (395 lines)
- Classes: TranslationRequest, TranslationResult, BaseTranslator, FallbackTranslator, GoogleTranslateAPI, DeepLAPI, OpenAITranslator, TranslatorService
- Functions: get_service, is_probably_thai, smart_translate_to_thai

## extracted_repo/app/services/wave_service.py (252 lines)
- Functions: _neutral_payload, _merge_dict, _fmt_num, analyze_wave, build_brief_message

## extracted_repo/app/settings/alerts.py (55 lines)
- Classes: AlertSettings

## extracted_repo/app/utils/__init__.py (5 lines)

## extracted_repo/app/utils/crypto_price.py (278 lines)
- Classes: _Resolver
- Functions: _cache_key, _get_cached, _set_cache, _run_async, fetch_price, fetch_price_text, _split_pair_token, resolve_symbol_vs_from_text, fetch_price_text_auto

## extracted_repo/app/utils/logging_tools.py (9 lines)
- Functions: setup_logging

## extracted_repo/app/utils/math_tools.py (1 lines)

## extracted_repo/app/utils/settings.py (37 lines)
- Classes: Settings

## extracted_repo/app/utils/state_store.py (66 lines)
- Functions: get_state, set_baseline, mark_alerted, should_alert, reset_state

## extracted_repo/app/utils/time_tools.py (1 lines)

## extracted_repo/backtest/__init__.py (1 lines)

## extracted_repo/backtest/fib_runner.py (230 lines)
- Functions: _find_close_col, _ensure_datetime_index, _local_extrema, _fib_ratio, run_fib_backtest, report

## extracted_repo/backtest/report.py (68 lines)
- Functions: generate_report

## extracted_repo/backtest/report_elliott.py (105 lines)
- Functions: generate_report

## extracted_repo/backtest/runner.py (150 lines)
- Functions: load_data, predict_dow, predict_elliott, run_backtest

## extracted_repo/backtest/sim_entry_exit.py (47 lines)
- Functions: generate_latest_signal

## extracted_repo/backtest/sim_longitudinal.py (199 lines)
- Functions: parse_timestamp_col, get_stage_from_result, make_event, summary_for_event, run_simulation, write_jsonl, write_markdown, main

## extracted_repo/backtest/sim_trade_plan.py (73 lines)
- Functions: get_btc_price, build_trade_plan

## extracted_repo/backtest/tp_sl_backtest.py (200 lines)
- Functions: _normalize_ohlc, _levels_for_side, _outcome_next_bars, run_backtest, main

## extracted_repo/backtest/watch_levels_backtest.py (224 lines)
- Functions: compute_atr14, parse_horizons, parse_buffer, build_watch_levels, hit_within_window, run_backtest, main

## extracted_repo/jobs/check_wave_stage.py (21 lines)
- Functions: main

## extracted_repo/jobs/daily_btc_analysis.py (175 lines)
- Functions: _now_utc_str, _excel_sanitize_datetimes, save_df_to_excel, send_line, main

## extracted_repo/jobs/push_btc_hourly.py (108 lines)
- Functions: _env, _get_bool_env, main

## extracted_repo/jobs/push_news.py (326 lines)
- Classes: _LineNotifier, NewsPushConfig, SentStore
- Functions: _truncate, _format_one, _join_items, run_push_news, _filter_by_keywords

## extracted_repo/jobs/watch_targets.py (124 lines)
- Functions: get_current_price, check_plan, check_all_plans, run_loop

## extracted_repo/load_image.py (44 lines)

## extracted_repo/scripts/analyze_and_push.py (93 lines)
- Functions: _env, _build_line_client, _build_argparser, main

## extracted_repo/scripts/analyze_chart.py (79 lines)
- Functions: ema, rsi, macd, analyze_sheet, generate_report, main

## extracted_repo/scripts/analyze_elliott_results.py (40 lines)

## extracted_repo/scripts/analyze_multi_tf.py (65 lines)
- Functions: pack_last

## extracted_repo/scripts/backtest_range.py (317 lines)
- Functions: _read_price_file, _call_dow, _last_window, _confirm_with_intraday, backtest_range

## extracted_repo/scripts/build_historical.py (134 lines)
- Functions: _download, _normalize_from_index, _resample_ohlcv, build_excel

## extracted_repo/scripts/build_historical_binance.py (181 lines)
- Functions: _ms, _fetch_klines, _to_df, fetch_interval, main

## extracted_repo/scripts/check_data.py (29 lines)
- Functions: check_data

## extracted_repo/scripts/debug_elliott_scope.py (40 lines)
- Functions: debug_elliott_scope

## extracted_repo/scripts/layers/config_layer.py (13 lines)

## extracted_repo/scripts/layers/data_layer.py (32 lines)
- Functions: load_data

## extracted_repo/scripts/layers/plot_layer.py (19 lines)
- Functions: plot_chart

## extracted_repo/scripts/mock_price_alert.py (98 lines)
- Functions: try_push_line, mock_prices_toward, fmt, main

## extracted_repo/scripts/mta_alert_bot.py (146 lines)
- Functions: _fmt, _send_line, _brief, _pick_bias, _fib_zone, run_symbol, main

## extracted_repo/scripts/mta_flow_demo.py (154 lines)
- Functions: _brief, main

## extracted_repo/scripts/multi_layer_smoke.py (37 lines)
- Functions: f

## extracted_repo/scripts/plot_chart.py (38 lines)

## extracted_repo/scripts/push_line_report.py (77 lines)
- Functions: chunk_text, _headers, check_env, check_profile, push_text, main

## extracted_repo/scripts/push_price_hourly.py (25 lines)
- Functions: main

## extracted_repo/scripts/scenario_engine.py (169 lines)
- Functions: last_vals, score_from_indicators, score_from_dow, score_from_elliott, normalize_to_pct, main

## extracted_repo/scripts/send_line_message.py (28 lines)
- Functions: push_text

## extracted_repo/scripts/show_history.py (19 lines)
- Functions: show_history

## extracted_repo/scripts/test_elliott_logic.py (19 lines)

## extracted_repo/scripts/test_elliott_periods.py (96 lines)
- Functions: load_df, slice_with_context, run_detector

## extracted_repo/scripts/test_push_btc_hourly.py (109 lines)
- Functions: _env, _get_bool_env, main

## extracted_repo/sim_trade_signal.py (235 lines)
- Functions: _atr_pct, _watch_levels_from_atr, _can_send_line, _line_token, _line_to_user, _push_line_text, _format_line_message, main

## extracted_repo/tests/__init__.py (1 lines)

## extracted_repo/tests/adapters/__init__.py (1 lines)

## extracted_repo/tests/adapters/test_price.py (10 lines)

## extracted_repo/tests/analysis/__init__.py (1 lines)

## extracted_repo/tests/analysis/test_analysis.py (26 lines)

## extracted_repo/tests/analysis/test_dow.py (33 lines)
- Functions: _make_trend_df, test_dow_uptrend, test_dow_downtrend

## extracted_repo/tests/analysis/test_elliott.py (29 lines)
- Functions: test_analyze_elliott_basic

## extracted_repo/tests/analysis/test_entry_exit.py (15 lines)

## extracted_repo/tests/analysis/test_fibonacci.py (22 lines)
- Functions: test_fib_levels_up, test_fib_levels_down, test_fib_extensions

## extracted_repo/tests/analysis/test_filters_sideway.py (38 lines)
- Functions: make_series, test_trend_and_volatility_pass_on_trending_market, test_volume_filter_runs, test_is_sideway_df_and_side_confidence_no_crash

## extracted_repo/tests/analysis/test_indicators.py (73 lines)
- Functions: make_df, test_ema_basic, test_rsi_within_bounds, test_macd_returns_three_series, test_adx_outputs_valid_range, test_stoch_kd_in_range, test_volume_metrics_returns_series, test_apply_indicators_adds_columns

## extracted_repo/tests/analysis/test_patterns.py (1 lines)

## extracted_repo/tests/engine/__init__.py (1 lines)

## extracted_repo/tests/engine/test_signal_engine.py (136 lines)
- Functions: make_df_from_closes, test_hold_when_insufficient_candles, test_open_long_when_sma_fast_gt_slow_and_green_candle, test_cooldown_blocks_immediate_reopen, test_no_flip_and_tp_close_flow, test_move_alerts_trigger_and_anchor_update, test_ai_toggle_changes_confidence_but_not_required

## extracted_repo/tests/features/__init__.py (1 lines)

## extracted_repo/tests/features/alerts/__init__.py (1 lines)

## extracted_repo/tests/features/alerts/test_alert.py (28 lines)

## extracted_repo/tests/features/alerts/test_broadcast.py (26 lines)

## extracted_repo/tests/features/replies/__init__.py (1 lines)

## extracted_repo/tests/features/replies/test_keyword_reply.py (18 lines)
- Functions: test_get_reply_keywords, test_parse_price_command_basic, test_parse_price_command_invalid

## extracted_repo/tests/logic/__init__.py (1 lines)

## extracted_repo/tests/logic/test_scenarios.py (37 lines)
- Functions: test_softmax_sum_100

## extracted_repo/tests/logic/test_strategies.py (29 lines)
- Functions: _sample_df, test_strategy_output

## extracted_repo/tests/logic/test_strategies_momentum.py (45 lines)
- Functions: make_series_trend, test_momentum_breakout_long_bias, test_momentum_breakout_short_bias

## extracted_repo/tests/routers/__init__.py (1 lines)

## extracted_repo/tests/routers/test_line_webhook_price.py (51 lines)
- Functions: test_price_command_btc

## extracted_repo/tests/services/__init__.py (1 lines)

## extracted_repo/tests/services/test_wave_service.py (34 lines)
- Functions: test_analyze_wave_includes_weekly_bias_in_message

## extracted_repo/tests/utils/__init__.py (1 lines)

## extracted_repo/tests/utils/test_price_ccxt.py (14 lines)
- Functions: test_fetch_price_from_binance, test_fetch_price_text_from_binance

## extracted_repo/tools/binance_dump.py (74 lines)
- Functions: to_ms, fetch_klines, download, main

## extracted_repo/worker.py (108 lines)
- Functions: print_config

