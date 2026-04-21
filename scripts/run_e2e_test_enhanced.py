#!/usr/bin/env python3
"""Enhanced E2E Test Script for Story Deconstruction Pipeline.

Features:
- Real-time progress monitoring
- Completeness validation (input/output)
- Error capture and diagnostics
- Detailed timing metrics
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph_agent.core.runner import run_skill

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class E2ETestMonitor:
    """Monitors and tracks E2E test progress."""
    
    def __init__(self, total_chapters: int):
        self.total_chapters = total_chapters
        self.completed_chapters = 0
        self.current_chapter = None
        self.start_time = None
        self.chapter_times = {}
        self.phase_times = {}
        self.errors = []
        
    def start(self):
        """Start monitoring."""
        self.start_time = time.time()
        print("=" * 70)
        print("ENHANCED E2E TEST - Story Deconstruction Pipeline")
        print("=" * 70)
        print(f"Total chapters to process: {self.total_chapters}")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 70)
        
    def update_chapter(self, chapter_number: int, phase: str = ""):
        """Update current chapter being processed."""
        self.current_chapter = chapter_number
        status = f"[Chapter {chapter_number}/{self.total_chapters}]"
        if phase:
            status += f" Phase: {phase}"
        print(f"\n{'>'*20} {status} {'<'*20}")
        
    def record_chapter_complete(self, chapter_number: int, duration: float):
        """Record chapter completion."""
        self.completed_chapters += 1
        self.chapter_times[chapter_number] = duration
        progress_pct = (self.completed_chapters / self.total_chapters) * 100
        print(f"✓ Chapter {chapter_number} completed in {duration:.2f}s")
        print(f"Progress: {self.completed_chapters}/{self.total_chapters} ({progress_pct:.1f}%)")
        
    def record_phase_time(self, phase: str, duration: float):
        """Record phase timing."""
        if phase not in self.phase_times:
            self.phase_times[phase] = []
        self.phase_times[phase].append(duration)
        
    def add_error(self, chapter: int, error: str):
        """Add error record."""
        self.errors.append({
            'chapter': chapter,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        
    def get_summary(self) -> dict:
        """Get test summary."""
        total_time = time.time() - self.start_time if self.start_time else 0
        return {
            'total_chapters': self.total_chapters,
            'completed_chapters': self.completed_chapters,
            'total_time_sec': total_time,
            'avg_time_per_chapter': total_time / self.completed_chapters if self.completed_chapters > 0 else 0,
            'chapter_times': self.chapter_times,
            'phase_times': {k: sum(v)/len(v) for k, v in self.phase_times.items()},
            'errors': self.errors
        }
        
    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        summary = self.get_summary()
        print(f"Total chapters: {summary['total_chapters']}")
        print(f"Completed: {summary['completed_chapters']}")
        print(f"Success rate: {(summary['completed_chapters']/summary['total_chapters'])*100:.1f}%")
        print(f"Total time: {summary['total_time_sec']:.2f}s")
        print(f"Avg per chapter: {summary['avg_time_per_chapter']:.2f}s")
        if summary['phase_times']:
            print("\nAverage phase times:")
            for phase, avg_time in summary['phase_times'].items():
                print(f"  {phase}: {avg_time:.2f}s")
        if summary['errors']:
            print(f"\nErrors ({len(summary['errors'])}):")
            for err in summary['errors']:
                print(f"  Chapter {err['chapter']}: {err['error']}")
        print("=" * 70)


class E2ETestRunner:
    """Enhanced E2E test runner."""
    
    EXPECTED_CHAPTERS = 25
    
    def __init__(self):
        self.monitor = None
        self.results = []
        self.output_dir = None
        
    def validate_input(self, input_data: dict) -> tuple[bool, str]:
        """Validate input has 25 chapters."""
        chapters = input_data.get('chapters', [])
        if not chapters:
            return False, "No chapters found in input"
        if len(chapters) != self.EXPECTED_CHAPTERS:
            return False, f"Expected {self.EXPECTED_CHAPTERS} chapters, got {len(chapters)}"
        # Check all chapters have required fields
        for i, ch in enumerate(chapters):
            if 'chapter_number' not in ch:
                return False, f"Chapter {i} missing chapter_number"
            if 'content' not in ch:
                return False, f"Chapter {i} missing content"
        return True, "Input validation passed"
        
    def validate_output(self) -> tuple[bool, list[str]]:
        """Validate output has 25 chapter results and event files."""
        errors = []
        
        if not self.output_dir or not self.output_dir.exists():
            return False, ["Output directory not found"]
            
        # Check for each chapter's output
        missing_chapters = []
        for i in range(1, self.EXPECTED_CHAPTERS + 1):
            chapter_file = self.output_dir / f"chapter_{i:03d}_events.json"
            if not chapter_file.exists():
                missing_chapters.append(i)
                
        if missing_chapters:
            errors.append(f"Missing event files for chapters: {missing_chapters}")
            
        # Check results file
        results_file = self.output_dir / "segmentation_results.json"
        if not results_file.exists():
            errors.append("Missing segmentation_results.json")
        else:
            try:
                with open(results_file) as f:
                    data = json.load(f)
                    if len(data.get('results', [])) != self.EXPECTED_CHAPTERS:
                        errors.append(f"Results count mismatch: expected {self.EXPECTED_CHAPTERS}")
            except Exception as e:
                errors.append(f"Failed to read results file: {e}")
                
        return len(errors) == 0, errors
        
    def run_chapter(self, chapter_data: dict) -> dict:
        """Process a single chapter."""
        chapter_number = chapter_data['chapter_number']
        content = chapter_data['content']
        
        chapter_start = time.time()
        chapter_result = {
            'chapter_number': chapter_number,
            'status': 'pending',
            'phases': {},
            'error': None
        }
        
        try:
            # Phase 1: Text Segmentation
            self.monitor.update_chapter(chapter_number, "text-segmentation")
            phase_start = time.time()
            
            seg_result = self._run_segmentation(chapter_number, content)
            chapter_result['phases']['segmentation'] = {
                'status': 'success',
                'duration': time.time() - phase_start,
                'segments': seg_result.get('segments', [])
            }
            
            # Phase 2: Event Extraction
            self.monitor.update_chapter(chapter_number, "event-extraction")
            phase_start = time.time()
            
            events = self._run_event_extraction(chapter_number, seg_result)
            chapter_result['phases']['extraction'] = {
                'status': 'success',
                'duration': time.time() - phase_start,
                'event_count': len(events)
            }
            
            chapter_result['status'] = 'success'
            chapter_result['events'] = events
            
        except Exception as e:
            chapter_result['status'] = 'failed'
            chapter_result['error'] = str(e)
            chapter_result['traceback'] = traceback.format_exc()
            self.monitor.add_error(chapter_number, str(e))
            logger.error(f"Chapter {chapter_number} failed: {e}")
            
        chapter_duration = time.time() - chapter_start
        self.monitor.record_chapter_complete(chapter_number, chapter_duration)
        
        return chapter_result
        
    def _run_segmentation(self, chapter_number: int, content: str) -> dict:
        """Run text segmentation skill."""
        skill_path = Path(__file__).resolve().parents[1] / 'skills' / 'text-segmentation'
        
        result = run_skill(skill_path, inputs={
            'chapter_number': chapter_number,
            'chapter_content': content
        })
        
        if not result.get('segmentation_result'):
            raise RuntimeError("Segmentation produced no result")
            
        return result['segmentation_result']
        
    def _run_event_extraction(self, chapter_number: int, seg_result: dict) -> list:
        """Run event extraction skill."""
        skill_path = Path(__file__).resolve().parents[1] / 'skills' / 'event-extraction'
        
        # For chapters after 1, get previous chapter's last event
        prev_last_event = None
        if chapter_number > 1 and self.results:
            prev_chapter = self.results[-1]
            if prev_chapter.get('events'):
                prev_last_event = prev_chapter['events'][-1]
        
        result = run_skill(skill_path, inputs={
            'chapter_number': chapter_number,
            'segments': seg_result.get('paragraphs', []),
            'prev_chapter_last_event': prev_last_event
        })
        
        return result.get('events', [])
        
    def save_results(self):
        """Save results to output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save individual chapter events
        for result in self.results:
            chapter_file = self.output_dir / f"chapter_{result['chapter_number']:03d}_events.json"
            with open(chapter_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
        # Save summary
        summary = {
            'project_id': 'e2e_test_enhanced',
            'total_chapters': len(self.results),
            'completed': sum(1 for r in self.results if r['status'] == 'success'),
            'failed': sum(1 for r in self.results if r['status'] == 'failed'),
            'results': self.results,
            'monitor_summary': self.monitor.get_summary()
        }
        
        summary_file = self.output_dir / "segmentation_results.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
    def run(self, input_path: Path, output_dir: Path) -> int:
        """Run the E2E test."""
        self.output_dir = output_dir
        
        try:
            # Load and validate input
            print(f"\n[1/5] Loading input from: {input_path}")
            with open(input_path, 'r', encoding='utf-8') as f:
                input_data = json.load(f)
                
            print(f"[2/5] Validating input...")
            is_valid, msg = self.validate_input(input_data)
            if not is_valid:
                print(f"✗ Input validation failed: {msg}")
                return 1
            print(f"✓ {msg}")
            
            # Initialize monitor
            self.monitor = E2ETestMonitor(len(input_data['chapters']))
            self.monitor.start()
            
            # Process each chapter
            print(f"\n[3/5] Processing chapters...")
            for chapter_data in input_data['chapters']:
                result = self.run_chapter(chapter_data)
                self.results.append(result)
                
                # Early termination check
                if result['status'] == 'failed':
                    print(f"\n⚠ Chapter {result['chapter_number']} failed - continuing...")
                    
            # Save results
            print(f"\n[4/5] Saving results...")
            self.save_results()
            print(f"✓ Results saved to: {output_dir}")
            
            # Validate output
            print(f"[5/5] Validating output...")
            is_output_valid, output_errors = self.validate_output()
            if not is_output_valid:
                print(f"✗ Output validation failed:")
                for err in output_errors:
                    print(f"  - {err}")
                return 1
            print(f"✓ Output validation passed")
            
            # Print final summary
            self.monitor.print_summary()
            
            success_count = sum(1 for r in self.results if r['status'] == 'success')
            if success_count == self.EXPECTED_CHAPTERS:
                print(f"\n✓ ALL {self.EXPECTED_CHAPTERS} CHAPTERS PROCESSED SUCCESSFULLY")
                return 0
            else:
                print(f"\n⚠ PARTIAL SUCCESS: {success_count}/{self.EXPECTED_CHAPTERS} chapters completed")
                return 1
                
        except KeyboardInterrupt:
            print("\n\n" + "=" * 70)
            print("TEST INTERRUPTED BY USER")
            print("=" * 70)
            self._print_diagnostics()
            return 130
            
        except Exception as e:
            print("\n\n" + "=" * 70)
            print("TEST FAILED WITH EXCEPTION")
            print("=" * 70)
            print(f"Error: {e}")
            print(f"\nTraceback:")
            traceback.print_exc()
            self._print_diagnostics()
            return 1
            
    def _print_diagnostics(self):
        """Print diagnostic information."""
        print("\n" + "-" * 70)
        print("DIAGNOSTIC INFORMATION")
        print("-" * 70)
        
        if self.monitor:
            print(f"\nProgress when stopped:")
            print(f"  Current chapter: {self.monitor.current_chapter}")
            print(f"  Completed: {self.monitor.completed_chapters}/{self.monitor.total_chapters}")
            if self.monitor.chapter_times:
                print(f"  Avg chapter time: {sum(self.monitor.chapter_times.values())/len(self.monitor.chapter_times):.2f}s")
                
        if self.results:
            print(f"\nResults summary:")
            successful = [r for r in self.results if r['status'] == 'success']
            failed = [r for r in self.results if r['status'] == 'failed']
            print(f"  Successful: {len(successful)}")
            print(f"  Failed: {len(failed)}")
            for r in failed[:5]:  # Show first 5 failures
                print(f"    - Chapter {r['chapter_number']}: {r.get('error', 'Unknown')}")
                
        print("\n" + "=" * 70)


def main():
    """Main entry point."""
    # Default paths
    project_root = Path(__file__).resolve().parents[1]
    input_path = project_root / 'skills' / 'story-deconstruction' / 'data' / 'e2e_test_input.json'
    output_dir = project_root / 'output' / 'e2e_test_enhanced'
    
    # Allow command-line override
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
        
    print(f"Input file: {input_path}")
    print(f"Output directory: {output_dir}")
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1
        
    runner = E2ETestRunner()
    return runner.run(input_path, output_dir)


if __name__ == '__main__':
    sys.exit(main())
