import 'package:flutter/material.dart';

import '../common/viewer_models.dart';

class ScatterController extends ChangeNotifier {
  String _query = '';
  String? _selectedId;
  bool _showLabels = false;
  bool _hideUnselectedCategories = false;
  String? _colorBy;
  String _featureQuery = '';

  String get query => _query;
  String? get selectedId => _selectedId;
  bool get showLabels => _showLabels;
  bool get hideUnselectedCategories => _hideUnselectedCategories;
  String? get colorBy => _colorBy;
  String get featureQuery => _featureQuery;

  set query(String value) {
    _query = value;
    if (value.trim().isNotEmpty) _selectedId = value.trim();
    notifyListeners();
  }

  void select(ScatterPointModel point) {
    _selectedId = point.id;
    notifyListeners();
  }

  void setShowLabels(bool value) {
    _showLabels = value;
    notifyListeners();
  }

  void setHideUnselectedCategories(bool value) {
    _hideUnselectedCategories = value;
    notifyListeners();
  }

  void setColorBy(String? value) {
    _colorBy = value;
    _featureQuery = '';
    notifyListeners();
  }

  void setFeatureQuery(String value) {
    _featureQuery = value;
    if (value.trim().isNotEmpty) _colorBy = null;
    notifyListeners();
  }

  void setInitialFeatureQuery(String value) {
    _featureQuery = value;
    if (value.trim().isNotEmpty) _colorBy = null;
  }

  void reset() {
    _query = '';
    _selectedId = null;
    _showLabels = false;
    _hideUnselectedCategories = false;
    _colorBy = null;
    _featureQuery = '';
    notifyListeners();
  }
}
