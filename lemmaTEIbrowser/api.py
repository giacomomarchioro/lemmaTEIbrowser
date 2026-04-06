
"""API routes for querying the TEI database."""

from flask import Blueprint, request, jsonify
from sqlalchemy import or_, func, text
from sqlalchemy.orm import joinedload

from .models import get_session, TextEntry, Word, Concept, Phraseme, PhrasemeWord

api_bp = Blueprint('api', __name__)


@api_bp.route('/occurrences', methods=['GET'])
def get_occurrences():
    """
    Unified search endpoint for words, phrasemes, and concepts.
    
    Query Parameters:
        q (str): Search query
        type (str): 'word', 'phraseme', 'concept', or 'all' (default)
        concept_id (int): Direct concept ID search
        notBefore (str): Filter by composition date
        notAfter (str): Filter by composition date
        text_id (str): Comma-separated text IDs
        page (int): Page number (default: 1)
        size (int): Results per page (default: 50)
    """
    session = get_session()
    
    try:
        # Pagination
        page = request.args.get('page', 1, type=int)
        size = min(request.args.get('size', 50, type=int), 500)
        offset = (page - 1) * size
        
        # Search parameters
        search_query = request.args.get('q')
        search_type = request.args.get('type', 'all')
        concept_id = request.args.get('concept_id', type=int)
        
        # Filters
        not_before = request.args.get('notBefore')
        not_after = request.args.get('notAfter')
        text_ids = request.args.get('text_id')
        
        results = []
        total_count = 0
        
        # Priority: concept_id search
        if concept_id:
            data = search_by_concept_id(
                session, concept_id, not_before, not_after, text_ids, offset, size
            )
            results = data['results']
            total_count = data['count']
        
        # Text-based search
        elif search_query:
            if search_type in ['concept', 'all']:
                data = search_by_concept(
                    session, search_query, not_before, not_after, text_ids, offset, size
                )
                results.extend(data['results'])
                total_count += data['count']
            
            if search_type in ['word', 'all']:
                data = search_by_word(
                    session, search_query, not_before, not_after, text_ids, offset, size
                )
                results.extend(data['results'])
                total_count += data['count']
            
            if search_type in ['phraseme', 'all']:
                data = search_by_phraseme(
                    session, search_query, not_before, not_after, text_ids, offset, size
                )
                results.extend(data['results'])
                total_count += data['count']
        else:
            return jsonify({'error': 'Either q or concept_id parameter required'}), 400
        
        # Pagination
        last_page = (total_count + size - 1) // size if total_count > 0 else 1
        
        # Extract unique texts
        text_dict = {}
        for result in results[:size]:
            tid = result['text']['id']
            if tid not in text_dict:
                text_dict[tid] = result['text']
        
        return jsonify({
            'api_version': 'v1',
            'last_page': last_page,
            'current_page': page,
            'per_page': size,
            'total_results': total_count,
            'data': results[:size],
            'texts': list(text_dict.values())
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


def search_by_concept_id(session, concept_id, not_before, not_after, text_ids, offset, size):
    """Search by exact concept ID."""
    concept = session.query(Concept).filter_by(id_concept=concept_id).first()
    if not concept:
        return {'results': [], 'count': 0}
    
    results = []
    
    # Words
    word_query = session.query(Word).options(
        joinedload(Word.text)
    ).filter(Word.id_concept == concept_id)
    word_query = apply_filters(word_query, Word, not_before, not_after, text_ids, session)
    
    total_words = word_query.count()
    words = word_query.limit(size).offset(offset).all()
    
    for w in words:
        results.append(build_word_result(w, concept))
    
    # Phrasemes
    phraseme_query = session.query(Phraseme).options(
        joinedload(Phraseme.text),
        joinedload(Phraseme.words).joinedload(PhrasemeWord.word)
    ).filter(Phraseme.id_concept == concept_id)
    phraseme_query = apply_filters(phraseme_query, Phraseme, not_before, not_after, text_ids, session)
    
    total_phrasemes = phraseme_query.count()
    remaining = size - len(results)
    phraseme_offset = max(0, offset - total_words)
    phrasemes = phraseme_query.limit(remaining).offset(phraseme_offset).all()
    
    for p in phrasemes:
        results.append(build_phraseme_result(p, concept))
    
    return {'results': results, 'count': total_words + total_phrasemes}


def search_by_concept(session, query, not_before, not_after, text_ids, offset, size):
    """Search by concept URL."""
    concept = session.query(Concept).filter(
        Concept.URLconcept.ilike(f'%{query}%')
    ).first()
    
    if not concept:
        return {'results': [], 'count': 0}
    
    return search_by_concept_id(session, concept.id_concept, not_before, not_after, text_ids, offset, size)


def search_by_word(session, query, not_before, not_after, text_ids, offset, size):
    """Search words by lemma or occurrence."""
    word_query = session.query(Word).options(
        joinedload(Word.text),
        joinedload(Word.concept)
    ).filter(
        or_(
            Word.lemma.ilike(f'%{query}%'),
            Word.occurrence.ilike(f'%{query}%')
        )
    )
    
    word_query = apply_filters(word_query, Word, not_before, not_after, text_ids, session)
    total = word_query.count()
    words = word_query.limit(size).offset(offset).all()
    
    results = [build_word_result(w) for w in words]
    return {'results': results, 'count': total}


def search_by_phraseme(session, query, not_before, not_after, text_ids, offset, size):
    """Search phrasemes by normalized form."""
    phraseme_query = session.query(Phraseme).options(
        joinedload(Phraseme.text),
        joinedload(Phraseme.concept),
        joinedload(Phraseme.words).joinedload(PhrasemeWord.word)
    ).filter(Phraseme.normalized_form.ilike(f'%{query}%'))
    
    phraseme_query = apply_filters(phraseme_query, Phraseme, not_before, not_after, text_ids, session)
    total = phraseme_query.count()
    phrasemes = phraseme_query.limit(size).offset(offset).all()
    
    results = [build_phraseme_result(p) for p in phrasemes]
    return {'results': results, 'count': total}


def apply_filters(query, model, not_before, not_after, text_ids, session):
    """Apply date and text_id filters."""
    if text_ids:
        ids = [int(tid.strip()) for tid in text_ids.split(',')]
        query = query.filter(model.id_text.in_(ids))
    
    if not_before or not_after:
        query = query.join(TextEntry)
        if not_before:
            query = query.filter(TextEntry.notBefore >= not_before)
        if not_after:
            query = query.filter(TextEntry.notAfter <= not_after)
    
    return query


def build_word_result(word, concept=None):
    """Build word result dictionary."""
    c = concept or word.concept
    return {
        'type': 'word',
        'id': word.id_word_entry,
        'xml_id': word.xml_id_word,
        'occurrence': word.occurrence,
        'lemma': word.lemma,
        'normalized_form': None,
        'concept': {
            'id': c.id_concept if c else None,
            'url': c.URLconcept if c else None
        },
        'context': word.context,
        'text': {
            'id': word.text.id,
            'author': word.text.author,
            'title': word.text.title,
            'notBefore': word.text.notBefore,
            'notAfter': word.text.notAfter
        }
    }


def build_phraseme_result(phraseme, concept=None):
    """Build phraseme result dictionary."""
    words_sorted = sorted(phraseme.words, key=lambda x: x.position)
    occurrence = ' '.join([pw.word.occurrence for pw in words_sorted if pw.word])
    xml_ids = [pw.word.xml_id_word for pw in words_sorted if pw.word]
    context = words_sorted[0].word.context if words_sorted and words_sorted[0].word else ''
    
    c = concept or phraseme.concept
    return {
        'type': 'phraseme',
        'id': phraseme.id,
        'xml_id': xml_ids,
        'occurrence': occurrence,
        'lemma': None,
        'normalized_form': phraseme.normalized_form,
        'concept': {
            'id': c.id_concept if c else None,
            'url': c.URLconcept if c else None
        },
        'context': context,
        'text': {
            'id': phraseme.text.id,
            'author': phraseme.text.author,
            'title': phraseme.text.title,
            'notBefore': phraseme.text.notBefore,
            'notAfter': phraseme.text.notAfter
        }
    }


@api_bp.route('/stats', methods=['GET'])
def get_statistics():
    """Get database statistics."""
    session = get_session()
    try:
        stats = {
            'texts': session.query(TextEntry).count(),
            'words': session.query(Word).count(),
            'concepts': session.query(Concept).count(),
            'phrasemes': session.query(Phraseme).count(),
            'unique_lemmas': session.query(func.count(func.distinct(Word.lemma))).scalar()
        }
        return jsonify({'data': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()
