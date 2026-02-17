#!/usr/bin/env python3
"""
Test script for Naga-7 Production Readiness Implementation.
Tests protobuf, correlation rules, playbook execution, and notifications.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_protobuf():
    """Test protobuf schema generation and usage"""
    print("\n=== Testing Protobuf Schemas ===")
    try:
        from schemas.events_pb2 import Event as ProtoEvent
        from schemas.alerts_pb2 import Alert as ProtoAlert
        from schemas.actions_pb2 import Action as ProtoAction
        
        # Create test event
        event = ProtoEvent(
            event_id="test-123",
            timestamp="2024-02-17T10:00:00Z",
            sentinel_id="sentinel-001",
            event_class="authentication",
            severity="high",
            raw_data='{"source_ip": "192.168.1.100", "outcome": "failure"}',
            enrichments='{}'
        )
        
        # Serialize and deserialize
        serialized = event.SerializeToString()
        deserialized = ProtoEvent()
        deserialized.ParseFromString(serialized)
        
        assert deserialized.event_id == "test-123"
        print("✅ Protobuf Event: OK")
        
        # Test Alert
        alert = ProtoAlert(
            alert_id="alert-456",
            created_at="2024-02-17T10:05:00Z",
            event_ids=["test-123"],
            threat_score=75,
            severity="high",
            status="new",
            verdict="pending",
            reasoning='{"rule": "Brute Force"}',
            affected_assets=["192.168.1.100"]
        )
        
        alert_bytes = alert.SerializeToString()
        print("✅ Protobuf Alert: OK")
        
        # Test Action
        action = ProtoAction(
            action_id="act-789",
            incident_id="inc-001",
            striker_id="striker-01",
            action_type="network_block",
            parameters='{"target": "192.168.1.100", "duration": 3600}',
            status="queued"
        )
        
        action_bytes = action.SerializeToString()
        print("✅ Protobuf Action: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Protobuf test failed: {e}")
        return False

async def test_correlation_rules():
    """Test correlation rules loading and structure"""
    print("\n=== Testing Correlation Rules ===")
    try:
        from n7_core.threat_correlator.correlation_rules import CORRELATION_RULES
        from n7_core.threat_correlator.service import ThreatCorrelatorService
        
        print(f"✅ Loaded {len(CORRELATION_RULES)} correlation rules")
        
        # Verify rule structure
        for rule_id, rule in CORRELATION_RULES.items():
            assert "name" in rule, f"Rule {rule_id} missing 'name'"
            assert "description" in rule, f"Rule {rule_id} missing 'description'"
            assert "severity" in rule, f"Rule {rule_id} missing 'severity'"
            assert "mitre_tactics" in rule, f"Rule {rule_id} missing 'mitre_tactics'"
            assert "mitre_techniques" in rule, f"Rule {rule_id} missing 'mitre_techniques'"
            print(f"  - {rule['name']}: {rule['description'][:50]}...")
        
        # Test ThreatCorrelator initialization
        correlator = ThreatCorrelatorService()
        assert len(correlator.rules) == len(CORRELATION_RULES)
        print("✅ ThreatCorrelator service: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Correlation rules test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_playbook_engine():
    """Test PlaybookEngine initialization and playbook loading"""
    print("\n=== Testing PlaybookEngine ===")
    try:
        from n7_core.playbook_engine.service import PlaybookEngine
        import tempfile
        import shutil
        
        # Create temporary playbook directory
        temp_dir = tempfile.mkdtemp()
        
        try:
            engine = PlaybookEngine(playbook_dir=temp_dir)
            
            # Start the engine to trigger sample playbook creation
            await engine.start()
            await asyncio.sleep(0.5)
            await engine.stop()
            
            # Check if sample playbook was created
            assert len(engine.playbooks) > 0, "No playbooks loaded"
            print(f"✅ PlaybookEngine loaded {len(engine.playbooks)} playbooks")
            
            # Verify playbook structure
            for pb_id, playbook in engine.playbooks.items():
                print(f"  - {playbook.get('name', pb_id)}")
                assert "steps" in playbook, f"Playbook {pb_id} missing steps"
                print(f"    Steps: {len(playbook['steps'])}")
            
            print("✅ PlaybookEngine: OK")
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"❌ PlaybookEngine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_services_import():
    """Test that all core services can be imported"""
    print("\n=== Testing Service Imports ===")
    try:
        from n7_core.audit_logger.service import AuditLoggerService
        print("✅ AuditLoggerService")
        
        from n7_core.notifier.service import NotifierService
        print("✅ NotifierService")
        
        from n7_core.threat_intel.service import ThreatIntelService
        print("✅ ThreatIntelService")
        
        from n7_core.enrichment.service import EnrichmentService
        print("✅ EnrichmentService")
        
        from n7_core.event_pipeline.service import EventPipelineService
        print("✅ EventPipelineService")
        
        from n7_core.threat_correlator.service import ThreatCorrelatorService
        print("✅ ThreatCorrelatorService")
        
        from n7_core.decision_engine.service import DecisionEngineService
        print("✅ DecisionEngineService")
        
        from n7_core.playbook_engine.service import PlaybookEngine
        print("✅ PlaybookEngine")
        
        return True
        
    except Exception as e:
        print(f"❌ Service import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_notification_channels():
    """Test notification service configuration"""
    print("\n=== Testing Notification Channels ===")
    try:
        from n7_core.notifier.service import NotifierService
        
        notifier = NotifierService()
        
        # Check configured channels based on actual attributes
        channels = []
        if hasattr(notifier, 'slack_webhook_url') and notifier.slack_webhook_url:
            channels.append("Slack")
        if hasattr(notifier, 'smtp_host') and notifier.smtp_host:
            channels.append("Email (SMTP)")
        if hasattr(notifier, 'pagerduty_key') and notifier.pagerduty_key:
            channels.append("PagerDuty")
        channels.append("Generic Webhook")  # Always available
        
        if channels:
            print(f"✅ Notification channels available: {', '.join(channels)}")
        else:
            print("ℹ️  No external notification channels configured (using defaults)")
        
        # Note: We won't actually send test notifications to avoid spam
        print("ℹ️  Actual notification sending not tested (requires external services)")
        
        return True
        
    except Exception as e:
        print(f"❌ Notification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("=" * 60)
    print("Naga-7 Production Readiness - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Protobuf Schemas", await test_protobuf()))
    results.append(("Correlation Rules", await test_correlation_rules()))
    results.append(("Playbook Engine", await test_playbook_engine()))
    results.append(("Service Imports", await test_services_import()))
    results.append(("Notification Channels", await test_notification_channels()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
