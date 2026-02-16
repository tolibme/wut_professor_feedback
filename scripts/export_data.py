"""
Data export script.

Exports professor feedbacks and statistics to CSV files.

Usage:
    python scripts/export_data.py [--output ./exports]
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from services.database_service import get_database_service
from services.analytics_service import get_analytics_service
from utils.logger import setup_logging


def export_professors(db, output_dir: Path) -> str:
    """Export all professors to CSV."""
    filepath = output_dir / "professors.csv"
    
    professors = db.get_all_professors()
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            "id", "name", "department", "courses",
            "overall_rating", "total_feedbacks",
            "positive_feedbacks", "negative_feedbacks", "neutral_feedbacks",
            "avg_teaching_quality", "avg_grading_fairness", "avg_workload",
            "avg_communication", "avg_engagement", "avg_exams_difficulty",
            "created_at", "updated_at"
        ])
        
        # Data
        for p in professors:
            writer.writerow([
                p.id, p.name, p.department,
                ";".join(p.courses or []),
                p.overall_rating, p.total_feedbacks,
                p.positive_feedbacks, p.negative_feedbacks, p.neutral_feedbacks,
                p.avg_teaching_quality, p.avg_grading_fairness, p.avg_workload,
                p.avg_communication, p.avg_engagement, p.avg_exams_difficulty,
                p.created_at, p.updated_at
            ])
    
    return str(filepath)


def export_feedbacks(db, output_dir: Path) -> str:
    """Export all feedbacks to CSV."""
    filepath = output_dir / "feedbacks.csv"
    
    # Get all professors first, then their feedbacks
    professors = db.get_all_professors()
    
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            "id", "professor_id", "professor_name",
            "course_code", "course_name", "semester",
            "sentiment", "explicit_rating", "inferred_rating", "final_rating",
            "extraction_confidence", "detected_language",
            "is_appropriate", "created_at",
            "original_message"
        ])
        
        # Data
        for professor in professors:
            feedbacks = db.get_professor_feedbacks(professor.id, limit=1000)
            
            for fb in feedbacks:
                writer.writerow([
                    fb.id, fb.professor_id, professor.name,
                    fb.course_code, fb.course_name, fb.semester,
                    fb.sentiment, fb.explicit_rating, fb.inferred_rating, fb.final_rating,
                    fb.extraction_confidence, fb.detected_language,
                    fb.is_appropriate, fb.created_at,
                    fb.original_message.replace("\n", " ")[:500]  # Truncate long messages
                ])
    
    return str(filepath)


def export_statistics(analytics, output_dir: Path) -> str:
    """Export statistics to text file."""
    filepath = output_dir / "statistics.txt"
    
    stats = analytics.get_overall_statistics()
    top_profs = analytics.get_top_professors(limit=20)
    bottom_profs = analytics.get_bottom_professors(limit=10)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("WUT Feedback Bot - Statistics Export\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("OVERALL STATISTICS\n")
        f.write("-" * 40 + "\n")
        f.write(f"Total Professors: {stats['total_professors']}\n")
        f.write(f"Total Feedbacks: {stats['total_feedbacks']}\n")
        f.write(f"Total Processed Messages: {stats['total_processed_messages']}\n")
        f.write(f"Total User Queries: {stats['total_queries']}\n")
        f.write(f"Average Rating: {stats['average_rating']:.2f}/5\n")
        f.write(f"Positive Feedbacks: {stats['positive_feedbacks']} ({stats['positive_percent']:.1f}%)\n")
        f.write(f"Negative Feedbacks: {stats['negative_feedbacks']} ({stats['negative_percent']:.1f}%)\n")
        f.write("\n")
        
        f.write("TOP 20 RATED PROFESSORS\n")
        f.write("-" * 40 + "\n")
        for prof in top_profs:
            f.write(f"{prof['rank']}. {prof['name']}\n")
            f.write(f"   Rating: {prof['rating']}/5 | Feedbacks: {prof['total_feedbacks']}\n")
            f.write(f"   Positive: {prof['positive_percent']:.0f}%\n")
        f.write("\n")
        
        f.write("BOTTOM 10 RATED PROFESSORS\n")
        f.write("-" * 40 + "\n")
        for prof in bottom_profs:
            f.write(f"{prof['rank']}. {prof['name']}\n")
            f.write(f"   Rating: {prof['rating']}/5 | Feedbacks: {prof['total_feedbacks']}\n")
            f.write(f"   Negative: {prof['negative_percent']:.0f}%\n")
        f.write("\n")
        
        if stats.get('departments'):
            f.write("DEPARTMENTS\n")
            f.write("-" * 40 + "\n")
            for dept, count in sorted(stats['departments'].items(), key=lambda x: -x[1]):
                f.write(f"  {dept}: {count} professors\n")
    
    return str(filepath)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export WUT Feedback Bot data to CSV"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./exports",
        help="Output directory for CSV files (default: ./exports)"
    )
    parser.add_argument(
        "--professors-only",
        action="store_true",
        help="Export only professors data"
    )
    parser.add_argument(
        "--feedbacks-only",
        action="store_true",
        help="Export only feedbacks data"
    )
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(Config.LOG_LEVEL)
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 50)
    print("WUT Feedback Bot - Data Export")
    print("=" * 50)
    print()
    
    # Initialize services
    print("Initializing services...")
    db = get_database_service()
    analytics = get_analytics_service()
    print("✓ Services initialized")
    print()
    
    # Export data
    files_created = []
    
    if not args.feedbacks_only:
        print("Exporting professors...")
        path = export_professors(db, output_dir)
        files_created.append(path)
        print(f"✓ Professors exported to {path}")
    
    if not args.professors_only:
        print("Exporting feedbacks...")
        path = export_feedbacks(db, output_dir)
        files_created.append(path)
        print(f"✓ Feedbacks exported to {path}")
    
    print("Exporting statistics...")
    path = export_statistics(analytics, output_dir)
    files_created.append(path)
    print(f"✓ Statistics exported to {path}")
    
    print()
    print("=" * 50)
    print("Export complete!")
    print("=" * 50)
    print()
    print("Files created:")
    for f in files_created:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
