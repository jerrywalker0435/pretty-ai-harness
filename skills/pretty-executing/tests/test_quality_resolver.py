#!/usr/bin/env python3
"""Regression tests for quality route selection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from quality_resolver import ROUTES, _matched_routes


class QualityResolverTest(unittest.TestCase):
    def test_only_specialized_routes_are_registered(self):
        self.assertEqual(
            {"MODULE_BOUNDARY", "TYPE_DESIGN", "JAVA_RUNTIME_RISK", "BEHAVIOR_TEST"},
            set(ROUTES),
        )

    def test_clean_code_patterns_do_not_select_an_extra_route(self):
        production_content = """
            public class OrderStrategy extends BaseStrategy implements Strategy {
                public Order execute(boolean dryRun) {
                    try {
                        return dryRun ? null : repository.load();
                    } catch (Exception error) {
                        return null;
                    }
                }
            }
        """

        self.assertEqual(set(), _matched_routes(production_content, ""))

    def test_specialized_facts_select_their_routes(self):
        production_content = """
            public interface OrderGateway {}
            record OrderId(String value) {}
            @Transactional
            Mono<Order> place(OrderId orderId) { return remoteClient.place(orderId); }
        """
        test_content = "assertThrows(OrderRejected.class, () -> service.place(orderId));"

        self.assertEqual(
            {"MODULE_BOUNDARY", "TYPE_DESIGN", "JAVA_RUNTIME_RISK", "BEHAVIOR_TEST"},
            _matched_routes(production_content, test_content),
        )


if __name__ == "__main__":
    unittest.main()
