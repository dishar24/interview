/**
 * Progress Chart - Skill Improvement Graph
 * Fetches data from /api/progress and displays:
 * - Overall score progression across attempts
 * - Skill-wise improvement across attempts
 */

let progressChart = null;

async function loadProgressChart() {
    try {
        // Fetch progress data from API
        const response = await fetch('/api/progress');
        if (!response.ok) {
            throw new Error(`API returned ${response.status}`);
        }
        
        const data = await response.json();
        
        // Check if there's any data
        if (!data.overall || data.overall.length === 0) {
            showNoDataMessage();
            return;
        }
        
        // Prepare datasets
        const datasets = [];
        
        // Overall score dataset (primary line, bold)
        const overallData = data.overall.map(point => ({
            x: point.attempt,
            y: point.score
        }));
        
        datasets.push({
            label: 'Overall Score',
            data: overallData,
            borderColor: 'rgb(13, 110, 253)',
            backgroundColor: 'rgba(13, 110, 253, 0.1)',
            borderWidth: 3,
            tension: 0.4,
            fill: true,
            pointRadius: 5,
            pointHoverRadius: 7
        });
        
        // Skill-wise datasets (thinner lines, different colors)
        const colors = [
            'rgb(25, 135, 84)',   // green
            'rgb(220, 53, 69)',   // red
            'rgb(255, 193, 7)',   // yellow
            'rgb(13, 202, 240)',  // cyan
            'rgb(111, 66, 193)',  // purple
            'rgb(253, 126, 20)',  // orange
            'rgb(214, 51, 132)',  // pink
            'rgb(32, 201, 151)'   // teal
        ];
        
        let colorIndex = 0;
        for (const [skill, points] of Object.entries(data.skills)) {
            const skillData = points.map(point => ({
                x: point.attempt,
                y: point.score
            }));
            
            const color = colors[colorIndex % colors.length];
            datasets.push({
                label: skill,
                data: skillData,
                borderColor: color,
                backgroundColor: color.replace('rgb', 'rgba').replace(')', ', 0.05)'),
                borderWidth: 2,
                tension: 0.4,
                fill: false,
                pointRadius: 4,
                pointHoverRadius: 6
            });
            
            colorIndex++;
        }
        
        // Get max attempt number for x-axis
        const maxAttempt = Math.max(...data.overall.map(p => p.attempt));
        
        // Create chart
        const ctx = document.getElementById('progressChart').getContext('2d');
        
        // Destroy existing chart if any
        if (progressChart) {
            progressChart.destroy();
        }
        
        progressChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Performance Improvement Across Interview Attempts',
                        font: {
                            size: 16,
                            weight: 'bold'
                        }
                    },
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            padding: 15,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14
                        },
                        bodyFont: {
                            size: 13
                        },
                        callbacks: {
                            title: function(context) {
                                return 'Attempt ' + context[0].parsed.x;
                            },
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y + '/100';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        title: {
                            display: true,
                            text: 'Interview Attempt',
                            font: {
                                size: 13,
                                weight: 'bold'
                            }
                        },
                        min: 1,
                        max: Math.max(maxAttempt, 3),
                        ticks: {
                            stepSize: 1,
                            callback: function(value) {
                                return Number.isInteger(value) ? value : '';
                            }
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Score (0-100)',
                            font: {
                                size: 13,
                                weight: 'bold'
                            }
                        },
                        min: 0,
                        max: 100,
                        ticks: {
                            stepSize: 10
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.1)'
                        }
                    }
                }
            }
        });
        
        // Hide no-data message if it was shown
        document.getElementById('noDataMessage').style.display = 'none';
        document.getElementById('chartContainer').style.display = 'block';
        
    } catch (error) {
        console.error('Failed to load progress chart:', error);
        showErrorMessage('Failed to load progress data. Please try refreshing the page.');
    }
}

function showNoDataMessage() {
    document.getElementById('chartContainer').style.display = 'none';
    document.getElementById('noDataMessage').style.display = 'block';
    document.getElementById('noDataMessage').innerHTML = `
        <div class="alert alert-info text-center">
            <i class="bi bi-graph-up" style="font-size: 3rem;"></i>
            <h5 class="mt-3">No Performance Data Yet</h5>
            <p>Complete at least one interview to see your progress graph.</p>
            <a href="${window.location.origin}/dashboard" class="btn btn-primary">Start an Interview</a>
        </div>
    `;
}

function showErrorMessage(message) {
    document.getElementById('chartContainer').style.display = 'none';
    document.getElementById('noDataMessage').style.display = 'block';
    document.getElementById('noDataMessage').innerHTML = `
        <div class="alert alert-warning text-center">
            <p>${message}</p>
        </div>
    `;
}

// Load chart when page is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadProgressChart);
} else {
    loadProgressChart();
}
