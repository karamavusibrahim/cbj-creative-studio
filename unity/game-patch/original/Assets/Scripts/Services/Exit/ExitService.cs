using System.Collections.Generic;
using UnityEngine;
using DG.Tweening;

public class ExitService : IExitService
{
    private readonly IGridManager _gridManager;
    private readonly GameManager _gameManager;

    public ExitService(IGridManager gridManager, GameManager gameManager)
    {
        _gridManager = gridManager;
        _gameManager = gameManager;
    }

    public bool CanBlockExit(Block block, Vector2Int gridPosition)
    {
        ExitData matchingExit = FindMatchingExit(block, gridPosition);
        if (matchingExit == null)
        {
            return false;
        }
        bool pathClear = IsPathClear(block, gridPosition, matchingExit);
        return pathClear;
    }

    private ExitData FindMatchingExit(Block block, Vector2Int gridPosition)
    {
        List<ExitData> exitDatas = _gridManager.LevelExits;
        
        HashSet<Vector2Int> blockCells = new HashSet<Vector2Int>();
        foreach (var offset in block.offsets)
        {
            blockCells.Add(gridPosition + offset);
        }

        foreach (var exitData in exitDatas)
        {
            if (exitData.requiredColor != block.GetBlockColor()) continue;

            HashSet<Vector2Int> exitCells = new HashSet<Vector2Int> { exitData.gridPosition };
            if (exitData.shapeOffsets != null)
            {
                foreach (var off in exitData.shapeOffsets)
                    exitCells.Add(exitData.gridPosition + off);
            }

            bool isOverlapping = false;
            foreach (var cell in blockCells)
            {
                if (exitCells.Contains(cell))
                {
                    isOverlapping = true;
                    break;
                }
            }

            if (isOverlapping)
            {
                return exitData;
            }
        }
        return null;
    }
    

    private bool IsPathClear(Block block, Vector2Int gridPosition, ExitData exitData)
    {
        Vector2Int direction = GetDirectionVector(exitData.direction);
        
        HashSet<int> exitIndices = new HashSet<int>();
        HashSet<Vector2Int> exitCells = new HashSet<Vector2Int> { exitData.gridPosition };
        if (exitData.shapeOffsets != null)
        {
            foreach (var off in exitData.shapeOffsets) exitCells.Add(exitData.gridPosition + off);
        }

        foreach(var cell in exitCells)
        {
            if (exitData.direction == ExitDirection.Left || exitData.direction == ExitDirection.Right)
                exitIndices.Add(cell.y);
            else
                exitIndices.Add(cell.x);
        }

        foreach (var blockOffset in block.offsets)
        {
            Vector2Int currentPartPos = gridPosition + blockOffset;
            Vector2Int checkPos = currentPartPos + direction;
            
            bool hitWallOrExit = false;
            int safetyCounter = 0;

            while (safetyCounter < 50) 
            {
                safetyCounter++;

                if (!_gridManager.IsInBounds(checkPos.x, checkPos.y))
                {
                    hitWallOrExit = true;
                    
                    int currentIndex = (exitData.direction == ExitDirection.Left || exitData.direction == ExitDirection.Right) 
                                     ? currentPartPos.y : currentPartPos.x;

                    if (!exitIndices.Contains(currentIndex))
                    {
                        return false; 
                    }
                    break; 
                }

                Cell cell = _gridManager.GetCell(checkPos.x, checkPos.y);
                if (cell != null && cell.item != null && cell.item != block)
                {
                    return false;
                }

                checkPos += direction;
            }
        }
        return true;
    }

    public void PerformExit(Block block)
    {
        if (block == null) return;
        
        Vector2Int gridPos = new Vector2Int(block.parentCell.column, block.parentCell.row);
        ExitData exitData = FindMatchingExit(block, gridPos);
        if (exitData == null)
        {
            Object.Destroy(block.gameObject);
            return;
        }
        
        ClearBlockFromGrid(block);
        DisableBlockColliders(block);

        // --- Setup Particle Tracking ---
        List<ParticleSystem> exitParticles = _gridManager.GetExitParticles(exitData.exitNumber);
        List<Vector3> exitCellWorldPositions = new List<Vector3>();
        
        if (exitParticles != null)
        {
            List<Vector2Int> points = new List<Vector2Int> { Vector2Int.zero };
            if (exitData.shapeOffsets != null) points.AddRange(exitData.shapeOffsets);
            
            foreach(var offset in points)
            {
                Vector2Int pos = exitData.gridPosition + offset;
                Vector3 worldPos = _gridManager.GridOrigin + new Vector3(pos.x * _gridManager.CellSpacing, 0, pos.y * _gridManager.CellSpacing);
                exitCellWorldPositions.Add(worldPos);
            }
        }
        // -------------------------------
        
        Vector2Int dirInt = GetDirectionVector(exitData.direction);
        Vector3 moveDir = new Vector3(dirInt.x, 0, dirInt.y);
        
        
        float distanceToClear = 0f;
        
        int minX = int.MaxValue, maxX = int.MinValue;
        int minY = int.MaxValue, maxY = int.MinValue;
        
        foreach(var offset in block.offsets)
        {
            Vector2Int partPos = gridPos + offset;
            if (partPos.x < minX) minX = partPos.x;
            if (partPos.x > maxX) maxX = partPos.x;
            if (partPos.y < minY) minY = partPos.y;
            if (partPos.y > maxY) maxY = partPos.y;
        }
        
        int gridW = _gridManager.GridWidth;
        int gridH = _gridManager.GridHeight;
        float extraBuffer = 2.0f;
        
        switch(exitData.direction)
        {
            case ExitDirection.Right: 
                distanceToClear = (gridW - minX) + extraBuffer;
                break;
                
            case ExitDirection.Left: 
                distanceToClear = (maxX + 1) + extraBuffer;
                break;
                
            case ExitDirection.Top: 
                distanceToClear = (gridH - minY) + extraBuffer;
                break;
                
            case ExitDirection.Bottom: 
                distanceToClear = (maxY + 1) + extraBuffer;
                break;
        }
        
        float worldDistance = distanceToClear * _gridManager.CellSpacing;
        Vector3 targetPos = block.transform.position + (moveDir * worldDistance);
        
        float durationPerCell = _gameManager.exitSpeedPerCell; 
        float totalDuration = distanceToClear * durationPerCell;
        
        Sequence exitSeq = DOTween.Sequence();
        
        // --- Exit Object Animation ---
        GameObject exitObj = _gridManager.GetExitObject(exitData.exitNumber);
        Vector3 exitInitialPos = Vector3.zero;
        
        if (exitObj != null)
        {
            exitInitialPos = exitObj.transform.position;
            
            // Animate down FIRST
            exitSeq.Append(exitObj.transform.DOMoveY(exitInitialPos.y - _gameManager.exitGoDownDepth, 0.1f)
                .SetEase(Ease.OutQuad));
        }
        // -----------------------------
        
        Tween moveTween = block.transform.DOMove(targetPos, totalDuration)
            .SetEase(_gameManager.blockExitAnimationCurve)
            .OnUpdate(() => {
                if (exitParticles != null && exitParticles.Count > 0)
                {
                    UpdateExitParticles(block, exitParticles, exitCellWorldPositions, exitData.direction);
                }
            });
            
        // THEN Block moves
        exitSeq.Append(moveTween);
        
        exitSeq.OnComplete(() => {
            if (exitParticles != null)
            {
                foreach(var ps in exitParticles) 
                {
                    if(ps != null && ps.isPlaying) ps.Stop(true, ParticleSystemStopBehavior.StopEmitting);
                }
            }
            
            _gameManager.OnBlockExited(block.gameObject);

            // Destroy Block
            Object.Destroy(block.gameObject);
            
            // --- Recover Exit Object ---
            if (exitObj != null)
            {
                exitObj.transform.DOMoveY(exitInitialPos.y, _gameManager.exitRecoveryDuration)
                    .SetEase(_gameManager.exitRecoveryCurver);
            }
            // ---------------------------
        });
    }

    private void UpdateExitParticles(Block block, List<ParticleSystem> particles, List<Vector3> exitCellPositions, ExitDirection direction)
    {
        float parallelThreshold = _gridManager.CellSpacing * 3.5f;
        float perpendicularThreshold = _gridManager.CellSpacing * 0.6f;
        
        float parallelThresholdSq = parallelThreshold * parallelThreshold;
        float perpendicularThresholdSq = perpendicularThreshold * perpendicularThreshold;

        for (int i = 0; i < particles.Count; i++)
        {
            if (particles[i] == null) continue;
            
            Vector3 exitPos = exitCellPositions[i];
            bool isCovered = false;
            
            foreach (var offset in block.offsets)
            {
                Vector3 partPos = block.transform.position + new Vector3(offset.x * _gridManager.CellSpacing, 0, offset.y * _gridManager.CellSpacing);
                
                float dx = Mathf.Abs(partPos.x - exitPos.x);
                float dz = Mathf.Abs(partPos.z - exitPos.z);
                
                bool isAligned = false;
                
                switch(direction)
                {
                    case ExitDirection.Left:
                    case ExitDirection.Right:
                        
                        if (dz < perpendicularThreshold && dx < parallelThreshold) isAligned = true;
                        break;
                    case ExitDirection.Top:
                    case ExitDirection.Bottom:
                 
                        if (dx < perpendicularThreshold && dz < parallelThreshold) isAligned = true;
                        break;
                }
                
                if (isAligned)
                {
                    isCovered = true;
                    break;
                }
            }
            
            if (isCovered)
            {
                if (!particles[i].isPlaying) 
                {
                    var main = particles[i].main;
                    main.loop = true;
                    particles[i].Play();
                }
            }
            else
            {
                if (particles[i].isPlaying) 
                {
                    particles[i].Stop(true, ParticleSystemStopBehavior.StopEmitting);
                }
            }
        }
    }

    private void DisableBlockColliders(Block block)
    {
        var colliders = block.GetComponentsInChildren<Collider>();
        foreach (var col in colliders)
        {
            col.enabled = false;
        }
    }

    private void ClearBlockFromGrid(Block block)
    {
        if (block.parentCell == null) return;
        
        Vector2Int pivot = new Vector2Int(block.parentCell.column, block.parentCell.row);
        
        foreach (var offset in block.offsets)
        {
            Vector2Int pos = pivot + offset;
            if (_gridManager.IsInBounds(pos.x, pos.y))
            {
                Cell cell = _gridManager.GetCell(pos.x, pos.y);
                if (cell.item == block)
                {
                    cell.item = null;
                }
            }
        }
    }
    private Vector2Int GetDirectionVector(ExitDirection direction)
    {
        return direction switch
        {
            ExitDirection.Left => Vector2Int.left,
            ExitDirection.Right => Vector2Int.right,
            ExitDirection.Top => Vector2Int.up,
            ExitDirection.Bottom => Vector2Int.down,
            _ => Vector2Int.zero
        };
    }

    private Vector3 GetWorldDirection(ExitDirection direction)
    {
        return direction switch
        {
            ExitDirection.Left => Vector3.left,
            ExitDirection.Right => Vector3.right,
            ExitDirection.Top => Vector3.forward,
            ExitDirection.Bottom => Vector3.back,
            _ => Vector3.zero
        };
    }
}
