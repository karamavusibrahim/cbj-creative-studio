using UnityEngine;
using DG.Tweening;

public class InputHandler : MonoBehaviour
{
    [Header("Settings")]
    [SerializeField] private LayerMask blockLayer;
    [SerializeField] private MovementSettings movementSettings;
    
    private IBlockMovementService _movementService;
    private IBlockGridService _gridService;
    private IExitService _exitService;
    private IGridManager _gridManager;
    
    private Block _currentBlock;
    private Vector3 _dragOffset;
    private float _initialY;
    private Plane _dragPlane;

    public float outlineWidth;

    
    private void Start()
    {
        InitializeServices();
    }

    private void InitializeServices()
    {
        _gridManager = GameManager.Instance.GridManager;
        _movementService = new BlockMovementService(_gridManager, movementSettings);
        _gridService = new BlockGridService(_gridManager);
        _exitService = new ExitService(_gridManager,GameManager.Instance);
    }

    private void Update()
    {
        HandleInput();
    }

    private void HandleInput()
    {
        // cbj-creative patch: after the win or fail screen, the board takes no more input
        // (it raycasts physics, so the overlay alone does not block drags).
        if (GameManager.Instance != null && GameManager.Instance.IsLevelOver)
        {
            if (_currentBlock != null) ReleaseBlock();
            return;
        }
        if (Input.GetMouseButtonDown(0))
        {
            if (GameManager.Instance != null)
            {
                GameManager.Instance.StartTimer();
            }
            TryPickupBlock();
        }
        else if (Input.GetMouseButton(0) && _currentBlock != null)
        {
            DragBlock();
        }
        else if (Input.GetMouseButtonUp(0) && _currentBlock != null)
        {
            ReleaseBlock();
        }
    }

    private void TryPickupBlock()
    {
        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);
        
        if (Physics.Raycast(ray, out RaycastHit hit, Mathf.Infinity, blockLayer))
        {
            Block block = hit.collider.GetComponentInParent<Block>();
            
            if (block != null && block.CanMove())
            {
                PickupBlock(block, ray);
            }
        }
    }

    private void PickupBlock(Block block, Ray ray)
    {
        _currentBlock = block;
        _initialY = block.transform.position.y;
        
        var outline = block.GetComponent<Outline>();
        if (outline != null)
        {
            outline.enabled = true;
            outline.OutlineWidth = outlineWidth;
        }

        _dragPlane = new Plane(Vector3.up, new Vector3(0, _initialY, 0));
        
        if (_dragPlane.Raycast(ray, out float enter))
        {
            Vector3 hitPoint = ray.GetPoint(enter);
            _dragOffset = block.transform.position - hitPoint;
        }
        else
        {
            _dragOffset = Vector3.zero;
        }
        block.transform.DOMoveY(_initialY + movementSettings.liftHeight, movementSettings.liftDuration)
            .SetEase(Ease.OutBack);
    }

    private void DragBlock()
    {
        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);
        if (_dragPlane.Raycast(ray, out float enter))
        {
            Vector3 hitPoint = ray.GetPoint(enter);
            Vector3 targetPos = new Vector3(
                hitPoint.x + _dragOffset.x,
                _initialY,
                hitPoint.z + _dragOffset.z
            );
            
            Vector3 currentPos = _currentBlock.transform.position;
            Vector3 newPos = _movementService.CalculateMovement(_currentBlock, currentPos, targetPos);
            
            newPos.y = _initialY + movementSettings.liftHeight;
            
            _currentBlock.transform.position = Vector3.Lerp(
                currentPos, 
                newPos, 
                Time.deltaTime * movementSettings.dragSpeed
            );

            // Update logical position during drag
            Vector2Int currentGridPos = _gridService.WorldToGridPosition(_currentBlock.transform.position);
            Vector2Int oldGridPos = new Vector2Int(_currentBlock.parentCell.column, _currentBlock.parentCell.row);
            
            if (currentGridPos != oldGridPos)
            {
                _gridService.UpdateBlockPosition(_currentBlock, currentGridPos);
                
                // Check for exit during drag
                if (_exitService.CanBlockExit(_currentBlock, currentGridPos))
                {
                    HandleExitDuringDrag(currentGridPos);
                }
            }
        }
    }

    private void HandleExitDuringDrag(Vector2Int gridPos)
    {
        Cell targetCell = _gridManager.GetCell(gridPos.x, gridPos.y);
        Vector3 snapPos = targetCell.transform.position;
        snapPos.y = _initialY; // Reset to ground level

        Block blockToExit = _currentBlock;
        _currentBlock = null; // Stop dragging
        
        var outline = blockToExit.GetComponent<Outline>();
        if (outline != null) outline.enabled = false;

        // Fast snap then exit
        blockToExit.transform.DOMove(snapPos, 0.1f)
            .SetEase(Ease.OutQuad)
            .OnComplete(() => {
                _exitService.PerformExit(blockToExit);
            });
    }

    private void ReleaseBlock()
    {
        Vector2Int gridPos = new Vector2Int(_currentBlock.parentCell.column, _currentBlock.parentCell.row);
        
        // Ensure grid is updated (though DragBlock should have handled it)
        _gridService.UpdateBlockPosition(_currentBlock, gridPos);
        
        Cell targetCell = _gridManager.GetCell(gridPos.x, gridPos.y);
        Vector3 snapPos = targetCell.transform.position;
        
        var outline = _currentBlock.GetComponent<Outline>();
        if (outline != null) outline.enabled = false;
        
        _currentBlock.transform.DOMove(snapPos, movementSettings.snapDuration)
            .SetEase(Ease.OutQuad);
        
        _currentBlock = null;
    }
}
