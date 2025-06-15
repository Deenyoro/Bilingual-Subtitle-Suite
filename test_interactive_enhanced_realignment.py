#!/usr/bin/env python3
"""
Test script for enhanced realignment in interactive mode.

This test verifies that interactive mode automatically enables enhanced realignment
for mixed track scenarios and provides feature parity with CLI mode.
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from ui.interactive import InteractiveInterface
from core.video_containers import VideoContainerHandler, SubtitleTrack
from utils.logging_config import get_logger

logger = get_logger(__name__)


def create_mock_video_tracks():
    """Create mock video tracks for testing."""
    # Mock embedded English track
    english_track = SubtitleTrack(
        track_id="2",
        language="eng",
        codec="subrip",
        title="English",
        default=True,
        forced=False
    )
    
    # Mock embedded Chinese track
    chinese_track = SubtitleTrack(
        track_id="3", 
        language="chi",
        codec="subrip",
        title="Chinese",
        default=False,
        forced=False
    )
    
    return [english_track, chinese_track]


def test_mixed_track_detection():
    """Test automatic mixed track scenario detection in interactive mode."""
    logger.info("🧪 TEST 1: Mixed Track Detection in Interactive Mode")
    
    # Create interactive interface
    interface = InteractiveInterface(use_colors=False)
    
    # Mock video path and external subtitle
    video_path = Path("test_video.mkv")
    chinese_sub = Path("test_video.zh.srt")
    
    # Mock video handler to return embedded English track
    with patch('core.video_containers.VideoContainerHandler') as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock tracks with embedded English
        mock_tracks = [
            MagicMock(language="eng", track_id="2"),
        ]
        mock_handler.list_subtitle_tracks.return_value = mock_tracks
        
        # Mock user input to enable enhanced realignment
        with patch('builtins.input', side_effect=['n', 'n', 'n', 'y']):  # Skip other options, enable mixed realignment
            try:
                options = interface._get_enhanced_alignment_options_with_mixed_detection(
                    video_path=video_path,
                    chinese_sub=chinese_sub,
                    english_sub=None
                )
                
                # Check that mixed realignment was enabled
                if options.get('enable_mixed_realignment', False):
                    logger.info("✅ TEST 1 PASSED: Mixed track scenario detected and enhanced realignment enabled")
                    return True
                else:
                    logger.error("❌ TEST 1 FAILED: Enhanced realignment not enabled for mixed scenario")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ TEST 1 FAILED: Exception during detection: {e}")
                return False


def test_interactive_feature_parity():
    """Test that interactive mode provides same features as CLI mode."""
    logger.info("🧪 TEST 2: Interactive Mode Feature Parity")
    
    interface = InteractiveInterface(use_colors=False)
    
    # Test that all CLI options are available in interactive mode
    cli_options = [
        'auto_align',
        'use_translation', 
        'alignment_threshold',
        'translation_api_key',
        'manual_align',
        'sync_strategy',
        'reference_language_preference',
        'force_pgs',
        'no_pgs',
        'enable_mixed_realignment'
    ]
    
    # Mock user inputs for all options
    with patch('builtins.input', side_effect=[
        'y',  # auto_align
        'y',  # use_translation
        'test_key',  # translation_api_key
        'y',  # manual_align
        '1',  # reference_language_preference (auto)
        '1',  # sync_strategy (auto)
        '0.8',  # alignment_threshold
        'n',  # force_pgs
        'n',  # no_pgs
    ]):
        with patch.dict('os.environ', {}, clear=True):  # Clear env vars
            try:
                options = interface._get_enhanced_alignment_options()
                
                # Check that all expected options are present
                missing_options = []
                for option in cli_options:
                    if option == 'enable_mixed_realignment':
                        continue  # This is handled separately
                    if option not in options:
                        missing_options.append(option)
                
                if not missing_options:
                    logger.info("✅ TEST 2 PASSED: All CLI options available in interactive mode")
                    return True
                else:
                    logger.error(f"❌ TEST 2 FAILED: Missing options: {missing_options}")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ TEST 2 FAILED: Exception during option gathering: {e}")
                return False


def test_automatic_enablement_logic():
    """Test the automatic enablement logic for mixed scenarios."""
    logger.info("🧪 TEST 3: Automatic Enablement Logic")
    
    interface = InteractiveInterface(use_colors=False)
    
    # Test Case 1: Mixed scenario (embedded English + external Chinese)
    video_path = Path("test_video.mkv")
    chinese_sub = Path("test_video.zh.srt")
    
    with patch('core.video_containers.VideoContainerHandler') as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock embedded English track
        mock_tracks = [MagicMock(language="eng")]
        mock_handler.list_subtitle_tracks.return_value = mock_tracks
        
        # Mock user accepting enhanced realignment
        with patch('builtins.input', side_effect=['n', 'n', 'n', 'y']):  # Skip other options, accept mixed realignment
            options1 = interface._get_enhanced_alignment_options_with_mixed_detection(
                video_path=video_path,
                chinese_sub=chinese_sub,
                english_sub=None
            )
    
    # Test Case 2: No mixed scenario (both external)
    with patch('builtins.input', side_effect=['n', 'n', 'n']):  # Skip all options
        options2 = interface._get_enhanced_alignment_options_with_mixed_detection(
            video_path=None,
            chinese_sub=chinese_sub,
            english_sub=Path("test_video.en.srt")
        )
    
    # Verify results
    mixed_enabled = options1.get('enable_mixed_realignment', False)
    no_mixed_enabled = options2.get('enable_mixed_realignment', False)
    
    if mixed_enabled and not no_mixed_enabled:
        logger.info("✅ TEST 3 PASSED: Automatic enablement logic works correctly")
        return True
    else:
        logger.error(f"❌ TEST 3 FAILED: Logic error - mixed: {mixed_enabled}, no_mixed: {no_mixed_enabled}")
        return False


def test_user_confirmation_workflow():
    """Test the user confirmation workflow for enhanced realignment."""
    logger.info("🧪 TEST 4: User Confirmation Workflow")
    
    interface = InteractiveInterface(use_colors=False)
    
    video_path = Path("test_video.mkv")
    chinese_sub = Path("test_video.zh.srt")
    
    with patch('core.video_containers.VideoContainerHandler') as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock embedded English track
        mock_tracks = [MagicMock(language="eng")]
        mock_handler.list_subtitle_tracks.return_value = mock_tracks
        
        # Test Case 1: User accepts enhanced realignment
        with patch('builtins.input', side_effect=['n', 'n', 'n', 'y']):  # Accept mixed realignment
            options_accept = interface._get_enhanced_alignment_options_with_mixed_detection(
                video_path=video_path,
                chinese_sub=chinese_sub,
                english_sub=None
            )
        
        # Test Case 2: User declines enhanced realignment
        with patch('builtins.input', side_effect=['n', 'n', 'n', 'n']):  # Decline mixed realignment
            options_decline = interface._get_enhanced_alignment_options_with_mixed_detection(
                video_path=video_path,
                chinese_sub=chinese_sub,
                english_sub=None
            )
    
    # Verify user choice is respected
    accept_enabled = options_accept.get('enable_mixed_realignment', False)
    decline_enabled = options_decline.get('enable_mixed_realignment', False)
    
    if accept_enabled and not decline_enabled:
        logger.info("✅ TEST 4 PASSED: User confirmation workflow works correctly")
        return True
    else:
        logger.error(f"❌ TEST 4 FAILED: User choice not respected - accept: {accept_enabled}, decline: {decline_enabled}")
        return False


def test_informational_display():
    """Test that informational messages are displayed correctly."""
    logger.info("🧪 TEST 5: Informational Display")
    
    interface = InteractiveInterface(use_colors=False)
    
    video_path = Path("test_video.mkv")
    chinese_sub = Path("test_video.zh.srt")
    
    with patch('core.video_containers.VideoContainerHandler') as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        # Mock embedded English track
        mock_tracks = [MagicMock(language="eng")]
        mock_handler.list_subtitle_tracks.return_value = mock_tracks
        
        # Capture stdout to verify informational messages
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with patch('builtins.input', side_effect=['n', 'n', 'n', 'y']):  # Accept mixed realignment
                options = interface._get_enhanced_alignment_options_with_mixed_detection(
                    video_path=video_path,
                    chinese_sub=chinese_sub,
                    english_sub=None
                )
                
                output = mock_stdout.getvalue()
                
                # Check for key informational messages
                required_messages = [
                    "MIXED TRACK SCENARIO DETECTED",
                    "Embedded track:",
                    "External track:",
                    "Enhanced realignment will:",
                    "Preserve embedded track timing",
                    "Shift external track timing"
                ]
                
                missing_messages = []
                for message in required_messages:
                    if message not in output:
                        missing_messages.append(message)
                
                if not missing_messages:
                    logger.info("✅ TEST 5 PASSED: All informational messages displayed correctly")
                    return True
                else:
                    logger.error(f"❌ TEST 5 FAILED: Missing messages: {missing_messages}")
                    return False


def main():
    """Run all interactive mode enhanced realignment tests."""
    logger.info("🚀 STARTING INTERACTIVE MODE ENHANCED REALIGNMENT TESTS")
    logger.info("=" * 80)
    
    tests = [
        test_mixed_track_detection,
        test_interactive_feature_parity,
        test_automatic_enablement_logic,
        test_user_confirmation_workflow,
        test_informational_display
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            logger.info("-" * 80)
        except Exception as e:
            logger.error(f"❌ TEST FAILED WITH EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            logger.info("-" * 80)
    
    logger.info("🏁 INTERACTIVE MODE TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Interactive mode enhanced realignment is fully functional.")
        logger.info("🎯 Feature parity achieved between CLI and interactive modes.")
        return True
    else:
        logger.error(f"💥 {total - passed} TESTS FAILED! Interactive mode needs fixes.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
