// Initialize Tabulator table
var table = new Tabulator("#results-table", {
    ajaxURL: "/api/v1/occurrences",
    pagination: true,
    paginationMode: "remote",
    paginationSize: 50,
    paginationSizeSelector: [25, 50, 100, 200],
    layout: "fitDataStretch",
    
    ajaxURLGenerator: function(url, config, params) {
        const searchQuery = document.getElementById('search-query').value;
        const conceptId = document.getElementById('concept-id').value;
        
        const urlParams = new URLSearchParams({
            page: params.page,
            size: params.size,
            type: document.getElementById('search-type').value,
            notBefore: document.getElementById('filter-notBefore').value,
            notAfter: document.getElementById('filter-notAfter').value,
            text_id: document.getElementById('filter-text-ids').value
        });
        
        // Priority to concept_id
        if (conceptId) {
            urlParams.set('concept_id', conceptId);
        } else if (searchQuery) {
            urlParams.set('q', searchQuery);
        }
        
        // Remove empty parameters
        for (let [key, value] of Array.from(urlParams.entries())) {
            if (!value) urlParams.delete(key);
        }
        
        return url + "?" + urlParams.toString();
    },
    
    columns: [
        {
            title: "Tipo",
            field: "type",
            width: 100,
            formatter: function(cell) {
                const value = cell.getValue();
                if (value === 'word') {
                    return '<span class="badge badge-blue">Parola</span>';
                }
                if (value === 'phraseme') {
                    return '<span class="badge badge-green">Frasema</span>';
                }
                return value;
            }
        },
        {title: "Occorrenza", field: "occurrence", width: 200},
        {title: "Lemma", field: "lemma", width: 150},
        {title: "Forma Norm.", field: "normalized_form", width: 150},
        {
            title: "Concetto",
            field: "concept.url",
            width: 200,
            formatter: function(cell) {
                const url = cell.getValue();
                if (!url) return '';
                const label = url.split('/').pop();
                return `<a href="${url}" target="_blank">${label}</a>`;
            }
        },
        {
            title: "Testo",
            field: "text",
            width: 300,
            formatter: function(cell) {
                const text = cell.getValue();
                return `${text.author}, <em>${text.title}</em> (${text.notBefore || '?'})`;
            }
        },
        {
            title: "Contesto",
            field: "context",
            width: 400,
            formatter: function(cell) {
                const context = cell.getValue();
                if (!context) return '';
                return '<span class="context">' + context.substring(0, 100) + '...</span>';
            }
        },
        {
            title: "XML ID",
            field: "xml_id",
            width: 150,
            formatter: function(cell) {
                const ids = cell.getValue();
                if (Array.isArray(ids)) {
                    return ids.join(', ');
                }
                return ids || '';
            }
        }
    ],
    
    ajaxResponse: function(url, params, response) {
        // Update stats
        const statsDiv = document.getElementById('stats');
        statsDiv.innerHTML = `
            <strong>Risultati:</strong> ${response.total_results} 
            <strong>Pagina:</strong> ${response.current_page} di ${response.last_page}
        `;
        return response;
    }
});

// Search button
document.getElementById('search-btn').addEventListener('click', function() {
    table.setPage(1);
    table.replaceData();
});

// Clear button
document.getElementById('clear-btn').addEventListener('click', function() {
    document.getElementById('search-query').value = '';
    document.getElementById('concept-id').value = '';
    document.getElementById('search-type').value = 'all';
    document.getElementById('filter-notBefore').value = '';
    document.getElementById('filter-notAfter').value = '';
    document.getElementById('filter-text-ids').value = '';
    document.getElementById('stats').innerHTML = '';
    table.clearData();
});

// Enter key to search
document.getElementById('search-query').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        document.getElementById('search-btn').click();
    }
});

document.getElementById('concept-id').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        document.getElementById('search-btn').click();
    }
});